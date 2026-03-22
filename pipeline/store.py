"""File store with archive/convert/validate tiers."""

import fnmatch
import glob as glob_mod
import hashlib
import json
import logging
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pipeline.manifest import get_source, list_sources, load_manifest
from pipeline.transforms import get_transform

logger = logging.getLogger(__name__)


class FileStore:
    """Manages data movement through archived -> converted -> validated tiers."""

    def __init__(self, base_dir: str | Path, manifest_path: str | Path | None = None):
        self.base = Path(base_dir)
        self.raw_dir = self.base / "raw"
        self.archived_dir = self.base / "archived"
        self.converted_dir = self.base / "converted"
        self.validated_dir = self.base / "validated"
        self.done_dir = self.base / "done"
        self.rejected_dir = self.base / "rejected"
        self.manifest = load_manifest(manifest_path)

    # -- Retrieve: raw -> archived -------------------------------------------

    def retrieve(self, source_id: str) -> list[Path]:
        """Copy raw files to archived/{source_id}/, or run scraper if configured."""
        cfg = get_source(source_id)

        # Check for scraper-based retrieval
        retrieval = cfg.get("origin", {}).get("retrieval", {})
        if retrieval.get("method") == "scrape":
            return self._retrieve_scrape(source_id, cfg)

        store_cfg = cfg.get("store", {})
        file_pattern = store_cfg.get("file_pattern")

        if file_pattern:
            return self._retrieve_pattern(source_id, file_pattern)

        logger.warning(
            "Source %s has no file_pattern defined, skipping retrieve",
            source_id,
        )
        return []

    def _retrieve_pattern(self, source_id: str, pattern: str) -> list[Path]:
        """Glob for files matching pattern in raw_dir and copy to archived/{source_id}/."""
        matches = sorted(glob_mod.glob(str(self.raw_dir / pattern)))
        if not matches:
            logger.warning("No files matching pattern %r for %s", pattern, source_id)
            return []

        dest_dir = self.archived_dir / source_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for match_path in matches:
            src = Path(match_path)
            dst = dest_dir / src.name
            shutil.copyfile(src, dst)
            meta = {
                "source_id": source_id,
                "file": src.name,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "size_bytes": dst.stat().st_size,
                "sha256": _sha256(dst),
            }
            logger.info("Archived: %s -> %s (%d bytes)", src, dst, meta["size_bytes"])
            _write_meta(dest_dir / f"{src.name}.meta.json", meta)
            results.append(dst)

        return results

    def _retrieve_scrape(self, source_id: str, cfg: dict) -> list[Path]:
        """Run a scraper script to populate archived/{source_id}/."""
        script = cfg["origin"]["retrieval"]["script"]
        dest_dir = self.archived_dir / source_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Resolve script path relative to project root (parent of data dir)
        project_root = self.base.parent
        script_path = project_root / script

        logger.info("Archived: running scraper %s for %s", script, source_id)
        result = subprocess.run(
            ["python", str(script_path), "--output-dir", str(dest_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("Scraper failed for %s: %s", source_id, result.stderr)
            msg = f"Scraper {script} failed (exit {result.returncode}): {result.stderr}"
            raise RuntimeError(msg)

        if result.stdout:
            logger.info("Scraper output: %s", result.stdout.strip())

        return sorted(f for f in dest_dir.iterdir() if not f.name.endswith(".json"))

    # -- Promote: archived -> converted --------------------------------------

    def promote_to_converted(self, source_id: str) -> list[Path]:
        """Extract/normalize archived files into converted/{source_id}/."""
        cfg = get_source(source_id)
        archived_dir = self.archived_dir / source_id
        converted_dir = self.converted_dir / source_id
        converted_dir.mkdir(parents=True, exist_ok=True)

        if not archived_dir.exists():
            logger.warning("No archived data for %s, run retrieve first", source_id)
            return []

        # Use per-source transform if registered
        transform = get_transform(source_id)
        if transform is not None:
            results = transform(archived_dir, converted_dir, cfg)
            logger.info("Converted: %s -> %d files (transform)", source_id, len(results))
            return results

        # Generic extraction fallback
        store_cfg = cfg.get("store", {})
        origin_cfg = cfg.get("origin", {})
        container = store_cfg.get("container")
        file_type = store_cfg.get("output_format") or origin_cfg.get("format", "csv")
        results = []

        for archived_file in sorted(archived_dir.iterdir()):
            if archived_file.suffix == ".json":
                continue  # skip metadata files

            if container == "zip" and archived_file.suffix == ".zip":
                pat = store_cfg.get("extract_pattern")
                results.extend(_extract_zip(archived_file, converted_dir, pattern=pat))
            elif file_type == "xlsx" and archived_file.suffix == ".xlsx":
                sheet_filter = store_cfg.get("sheet_name")
                results.extend(
                    _convert_xlsx(archived_file, converted_dir, sheet_name=sheet_filter)
                )
            elif archived_file.suffix == ".csv":
                dst = converted_dir / archived_file.name
                shutil.copyfile(archived_file, dst)
                results.append(dst)
                logger.info("Converted: copied %s", dst)

        logger.info("Converted: %s -> %d files", source_id, len(results))
        return results

    # -- Promote: converted -> validated -------------------------------------

    def promote_to_validated(self, source_id: str) -> list[Path]:
        """Validate converted files and promote to validated/{source_id}/."""
        cfg = get_source(source_id)
        converted_dir = self.converted_dir / source_id
        validated_dir = self.validated_dir / source_id
        validated_dir.mkdir(parents=True, exist_ok=True)

        if not converted_dir.exists():
            logger.warning("No converted data for %s, run promote_to_converted first", source_id)
            return []

        columns = cfg.get("store", {}).get("validated_columns", [])
        expected_targets = [c["target"] for c in columns] if columns else []

        # Pre-DB schema validation: check archived (raw) files against expected_columns.
        # This catches files with completely wrong schema before they enter the DB.
        schema_rejected: set[str] = set()
        expected_columns = cfg.get("quality", {}).get("expected_columns", [])
        if expected_columns:
            archived_dir = self.archived_dir / source_id
            if archived_dir.exists():
                for archived_file in sorted(archived_dir.iterdir()):
                    if archived_file.suffix not in (".csv", ".txt"):
                        continue
                    with open(archived_file, encoding="utf-8-sig", errors="replace") as f:
                        first_line = f.readline().strip()
                    if not first_line:
                        continue
                    file_cols = [c.strip().strip('"') for c in first_line.split(",")]
                    if file_cols != expected_columns:
                        logger.warning(
                            "Validated: archived file %s has columns %s, expected %s - rejecting",
                            archived_file.name,
                            file_cols,
                            expected_columns,
                        )
                        reason = f"Schema mismatch: got {file_cols}, expected {expected_columns}"
                        self._reject_file(
                            source_id,
                            archived_file,
                            reason,
                        )
                        schema_rejected.add(archived_file.stem)

        results = []

        for converted_file in sorted(converted_dir.iterdir()):
            if converted_file.suffix == ".json":
                continue

            # Skip files whose archived counterpart failed schema check
            if converted_file.stem in schema_rejected:
                logger.info("Validated: skipping %s (schema rejected)", converted_file.name)
                continue

            # Validation: non-empty
            if converted_file.stat().st_size == 0:
                logger.warning("Validated: skipping empty file %s", converted_file)
                continue

            # Validation: check validated_columns if defined
            if expected_targets and converted_file.suffix in (".csv", ".txt"):
                with open(converted_file, encoding="utf-8", errors="replace") as f:
                    first_line = f.readline().strip()
                if first_line:
                    file_cols = [c.strip() for c in first_line.split(",")]
                    missing = [t for t in expected_targets if t not in file_cols]
                    if missing:
                        logger.warning(
                            "Validated: %s missing columns %s, promoting anyway",
                            converted_file,
                            missing,
                        )

            dst = validated_dir / converted_file.name
            shutil.copyfile(converted_file, dst)
            results.append(dst)
            logger.info("Validated: validated and promoted %s", dst)

        logger.info("Validated: %s -> %d files", source_id, len(results))
        return results

    # -- File lifecycle: done / rejected -------------------------------------

    def _reject_file(self, source_id: str, file_path: Path, reason: str):
        """Move a file to rejected/{source_id}/ with a rejection log."""
        reject_dir = self.rejected_dir / source_id
        reject_dir.mkdir(parents=True, exist_ok=True)
        dst = reject_dir / file_path.name
        shutil.copyfile(file_path, dst)
        log_entry = {
            "source_id": source_id,
            "file": file_path.name,
            "rejected_at": datetime.now(UTC).isoformat(),
            "reason": reason,
        }
        log_path = reject_dir / f"{file_path.name}.rejection.json"
        _write_meta(log_path, log_entry)
        logger.warning("Rejected: %s -> %s (%s)", file_path.name, dst, reason)

    def move_file_to_done(self, source_id: str, filename: str):
        """Move a single archived file to done/{source_id}/."""
        done_dir = self.done_dir / source_id
        done_dir.mkdir(parents=True, exist_ok=True)
        archived_dir = self.archived_dir / source_id
        src = archived_dir / filename
        if not src.exists():
            logger.warning("Done: archived file not found: %s", src)
            return
        dst = done_dir / filename
        shutil.move(str(src), str(dst))
        logger.info("Done: %s -> %s", filename, dst)

    def move_file_to_rejected(self, source_id: str, filename: str, reason: str):
        """Move a single archived file to rejected/{source_id}/ with rejection log."""
        reject_dir = self.rejected_dir / source_id
        reject_dir.mkdir(parents=True, exist_ok=True)
        archived_dir = self.archived_dir / source_id
        src = archived_dir / filename
        if not src.exists():
            logger.warning("Rejected: archived file not found: %s", src)
            return
        dst = reject_dir / filename
        shutil.move(str(src), str(dst))
        log_entry = {
            "source_id": source_id,
            "file": filename,
            "rejected_at": datetime.now(UTC).isoformat(),
            "reason": reason,
        }
        _write_meta(reject_dir / f"{filename}.rejection.json", log_entry)
        logger.warning("Rejected: %s -> %s (%s)", filename, dst, reason)

    # -- Query -------------------------------------------------------------

    def get_validated_files(self, source_id: str) -> list[Path]:
        """Return validated-tier files for a source."""
        validated_dir = self.validated_dir / source_id
        if not validated_dir.exists():
            return []
        return sorted(f for f in validated_dir.iterdir() if not f.name.endswith(".json"))

    def status(self) -> dict:
        """Return tier status for all sources."""
        result = {}
        for sid in list_sources():
            result[sid] = {}
            for tier_name, tier_dir in [
                ("archived", self.archived_dir),
                ("converted", self.converted_dir),
                ("validated", self.validated_dir),
                ("done", self.done_dir),
                ("rejected", self.rejected_dir),
            ]:
                d = tier_dir / sid
                if d.exists():
                    files = [f for f in d.iterdir() if not f.name.endswith(".json")]
                    total_bytes = sum(f.stat().st_size for f in files)
                    result[sid][tier_name] = {
                        "file_count": len(files),
                        "total_bytes": total_bytes,
                    }
                else:
                    result[sid][tier_name] = {"file_count": 0, "total_bytes": 0}
        return result


# -- Helpers ---------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_meta(path: Path, meta: dict):
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)


def _extract_zip(zip_path: Path, dest_dir: Path, pattern: str | None = None) -> list[Path]:
    results = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if pattern and not fnmatch.fnmatch(Path(name).name, pattern):
                continue
            extracted = dest_dir / Path(name).name  # flatten directory structure
            with zf.open(name) as src, open(extracted, "wb") as dst:
                shutil.copyfileobj(src, dst)
            results.append(extracted)
            logger.info("Converted: extracted %s", extracted)
    return results


def _convert_xlsx(xlsx_path: Path, dest_dir: Path, sheet_name: str | None = None) -> list[Path]:
    """Convert XLSX sheets to CSV. If sheet_name is set, only convert that sheet."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    results = []
    stem = xlsx_path.stem

    sheets_to_convert = [sheet_name] if sheet_name else wb.sheetnames

    for sn in sheets_to_convert:
        if sn not in wb.sheetnames:
            logger.warning("Sheet %r not found in %s, skipping", sn, xlsx_path.name)
            continue
        ws = wb[sn]
        safe_sheet = sn.replace(" ", "_").replace("/", "_")
        csv_name = f"{stem}_{safe_sheet}.csv" if len(sheets_to_convert) > 1 else f"{stem}.csv"
        csv_path = dest_dir / csv_name

        with open(csv_path, "w", newline="") as f:
            import csv

            writer = csv.writer(f)
            for row in ws.iter_rows(values_only=True):
                writer.writerow(row)

        results.append(csv_path)
        logger.info("Converted: converted %s [%s] -> %s", xlsx_path.name, sn, csv_path)

    wb.close()
    return results


def compute_file_manifest(directory: Path) -> list[dict]:
    """Return sorted manifest of CSV files: [{filename, sha256, size_bytes}, ...]."""
    manifest = []
    for f in sorted(directory.iterdir()):
        if f.suffix != ".csv":
            continue
        manifest.append(
            {
                "filename": f.name,
                "sha256": _sha256(f),
                "size_bytes": f.stat().st_size,
            }
        )
    return manifest


def compute_composite_hash(manifest: list[dict]) -> str:
    """Hash sorted manifest sha256 values into a single composite hash."""
    if not manifest:
        return ""
    sorted_manifest = sorted(manifest, key=lambda m: m["filename"])
    combined = "".join(m["sha256"] for m in sorted_manifest)
    return hashlib.sha256(combined.encode()).hexdigest()
