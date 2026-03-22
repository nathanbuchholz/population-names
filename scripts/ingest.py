"""Ingest validated CSV files into raw.* tables using psycopg2."""

import argparse
import csv
import glob
import io
import logging
import os
import sys
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Add project root to path so pipeline package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.manifest import get_source, list_sources  # noqa: E402
from pipeline.store import compute_composite_hash, compute_file_manifest  # noqa: E402


def get_conn():
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC environment variable is required")
    return psycopg2.connect(url)


_default_data = os.path.join(os.path.dirname(__file__), "..", "data", "validated")
DATA_DIR = os.environ.get("DATA_DIR", _default_data)


def _get_last_successful_hash(cur, source_id):
    """Compute the composite hash from the most recent successful batch's per-file hashes."""
    cur.execute(
        "SELECT filename, file_hash FROM raw.file_log "
        "WHERE source_id = %s AND status = 'success' "
        "AND started_at = ("
        "  SELECT max(started_at) FROM raw.file_log "
        "  WHERE source_id = %s AND status = 'success'"
        ") "
        "ORDER BY filename",
        (source_id, source_id),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    manifest = [{"filename": r[0], "sha256": r[1]} for r in rows]
    return compute_composite_hash(manifest)


def truncate_table(cur, table):
    cur.execute(f"TRUNCATE TABLE {table}")  # noqa: S608


def ingest_source(conn, source_id, force=False):
    """Generic CSV-to-table ingestion for any source, with change detection."""
    cfg = get_source(source_id)
    db_cfg = cfg.get("db", {})
    table = db_cfg.get("table")
    columns = db_cfg.get("columns", [])

    if not table or not columns:
        logger.warning("No db config for %s, skipping", source_id)
        return

    source_dir = Path(os.path.join(DATA_DIR, source_id))

    # Compute file manifest and composite hash
    if source_dir.exists():
        manifest = compute_file_manifest(source_dir)
    else:
        manifest = []
    composite_hash = compute_composite_hash(manifest)

    cur = conn.cursor()

    try:
        # Check if files have changed since last successful ingestion
        last_hash = _get_last_successful_hash(cur, source_id)

        if last_hash == composite_hash and not force:
            logger.info("%s: skipped (unchanged)", source_id)
            return

        # TRUNCATE + reload
        truncate_table(cur, table)

        files = sorted(glob.glob(os.path.join(str(source_dir), "*.csv")))
        if not files:
            logger.warning("%s: no CSV files found in %s", source_id, source_dir)

        # Build column list with file_log_id appended
        data_col_names = ", ".join(columns)
        all_col_names = f"{data_col_names}, file_log_id"

        batch_start = None
        cur.execute("SELECT NOW()")
        batch_start = cur.fetchone()[0]

        total_count = 0
        for filepath in files:
            file_entry = next((m for m in manifest if m["filename"] == Path(filepath).name), None)

            # Insert file_log row (status=success, will update row_count after COPY)
            cur.execute(
                "INSERT INTO raw.file_log "
                "(source_id, filename, file_hash, file_size_bytes, status, forced, started_at) "
                "VALUES (%s, %s, %s, %s, 'success', %s, %s) RETURNING id",
                (
                    source_id,
                    Path(filepath).name,
                    file_entry["sha256"] if file_entry else None,
                    file_entry["size_bytes"] if file_entry else None,
                    force,
                    batch_start,
                ),
            )
            file_log_id = cur.fetchone()[0]

            buf = io.StringIO()
            writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
            file_count = 0
            with open(filepath) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    values = [row.get(col, "") or "" for col in columns]
                    values.append(str(file_log_id))
                    writer.writerow(values)
                    file_count += 1
            buf.seek(0)
            cur.copy_expert(
                f"COPY {table} ({all_col_names}) FROM STDIN WITH (FORMAT text, NULL '')",  # noqa: S608
                buf,
            )

            # Update row_count and completed_at
            cur.execute(
                "UPDATE raw.file_log SET row_count = %s, completed_at = NOW() WHERE id = %s",
                (file_count, file_log_id),
            )
            total_count += file_count

        if total_count == 0 and files:
            conn.rollback()
            raise RuntimeError(f"{source_id}: ingested 0 rows from {len(files)} files")

        conn.commit()
        logger.info("%s: inserted %d rows", source_id, total_count)

    except Exception as e:
        conn.rollback()
        # Log failure in a new transaction - one row per file
        try:
            for entry in manifest:
                cur.execute(
                    "INSERT INTO raw.file_log "
                    "(source_id, filename, file_hash, file_size_bytes, "
                    "status, error_message, forced, completed_at) "
                    "VALUES (%s, %s, %s, %s, 'failed', %s, %s, NOW())",
                    (
                        source_id,
                        entry["filename"],
                        entry["sha256"],
                        entry["size_bytes"],
                        str(e),
                        force,
                    ),
                )
            if not manifest:
                cur.execute(
                    "INSERT INTO raw.file_log "
                    "(source_id, filename, status, error_message, forced, completed_at) "
                    "VALUES (%s, %s, 'failed', %s, %s, NOW())",
                    (source_id, "", str(e), force),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        cur.close()


# All sources in the manifest that have db.columns defined are ingestable
SOURCES = {sid: sid for sid in list_sources() if get_source(sid).get("db", {}).get("columns")}
HANDLERS = SOURCES


def main():
    parser = argparse.ArgumentParser(description="Ingest raw name data")
    parser.add_argument("--source", choices=list(SOURCES.keys()), help="Single source to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all sources")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion even if files unchanged",
    )
    args = parser.parse_args()

    if not args.source and not args.all:
        parser.error("Specify --source=NAME or --all")

    conn = get_conn()

    try:
        if args.all:
            for source_id in SOURCES:
                logger.info("Ingesting %s...", source_id)
                ingest_source(conn, source_id, force=args.force)
        else:
            ingest_source(conn, args.source, force=args.force)
        logger.info("Ingestion complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
