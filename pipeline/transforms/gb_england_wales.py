"""Transforms for England & Wales data sources."""

import re
from pathlib import Path

from pipeline.transforms import read_xlsx_rows, register, resolve_schema_version, write_csv


def _extract_ons_sheet(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """Extract forename data from ONS XLSX sheets using schema version config.

    Schema version provides:
      - sheet_candidates: which sheet names to try
      - skip_rows: metadata rows to skip
      - notes_before_header: whether to scan forward for the header row
    """
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".xlsx":
            continue

        fname = archived_file.name.lower()
        if "boy" in fname:
            sex = "M"
        elif "girl" in fname:
            sex = "F"
        else:
            continue

        version = resolve_schema_version(archived_file.name, cfg)

        # Extract year from filename
        year_match = re.search(r"(\d{4})", archived_file.name)
        year = int(year_match.group(1)) if year_match else 2024

        sheet_candidates = version.get("sheet_candidates", ["Table_2"])
        skip_rows = version.get("skip_rows", 4)
        notes_before_header = version.get("notes_before_header", False)

        # Try candidate sheet names until one is found
        rows = []
        for sheet_name in sheet_candidates:
            rows = read_xlsx_rows(archived_file, sheet_name, skip_rows=skip_rows)
            if rows:
                break

        if not rows:
            continue

        # Find the header row if there are note rows before it
        header_idx = 0
        if notes_before_header:
            for i, row in enumerate(rows):
                cell0 = str(row[0]).strip() if row[0] else ""
                cell1 = str(row[1]).strip() if row[1] else ""
                if cell0.lower() in ("rank",) or cell1.lower() in ("name",):
                    header_idx = i
                    break

        # Data starts after the header row
        data_rows = []
        for row in rows[header_idx + 1 :]:
            rank, name, count = row[0], row[1], row[2]
            if name is None or count is None:
                continue
            data_rows.append([name, sex, count, rank, year])

        out_name = archived_file.stem + ".csv"
        out_path = converted_dir / out_name
        results.append(write_csv(out_path, ["name", "sex", "count", "rank", "year"], data_rows))

    return results


@register("ons_forenames")
def transform_ons_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    return _extract_ons_sheet(archived_dir, converted_dir, cfg)


@register("wales_forenames")
def transform_wales_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    return _extract_ons_sheet(archived_dir, converted_dir, cfg)


@register("england_surnames")
def transform_england_surnames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    import csv as csv_mod

    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".csv":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        col_map = version.get("columns", {"name": "Surname", "count": "Count"})

        with open(archived_file, encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            data_rows = []
            for row in reader:
                name = row.get(col_map["name"], "").strip()
                count = row.get(col_map["count"], "").strip()
                if not name or not count:
                    continue
                data_rows.append([name, int(count), 2014])

        out_path = converted_dir / archived_file.name
        results.append(write_csv(out_path, ["name", "count", "year"], data_rows))

    return results
