"""Per-file quality gate: check rejection rates and route files to done/rejected."""

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Add project root to path so pipeline package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.manifest import get_source  # noqa: E402
from pipeline.store import FileStore  # noqa: E402

_default = Path(__file__).resolve().parent.parent / "data" / "validated"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default)).resolve()
# FileStore expects the base data directory (parent of validated/)
STORE_BASE = DATA_DIR.parent


def get_conn():
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC environment variable is required")
    return psycopg2.connect(url)


def quality_gate(source_id: str) -> int:
    """Evaluate per-file quality and route files. Returns exit code: 0/1/2."""
    cfg = get_source(source_id)
    threshold = cfg.get("quality", {}).get("max_rejected_pct", 5)
    db_cfg = cfg.get("db", {})
    table_name = db_cfg.get("table", "").replace("raw.", "")

    if not table_name:
        print(f"No db.table configured for {source_id}, skipping quality gate")
        return 0

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Find the latest batch for this source
        cur.execute(
            "SELECT started_at FROM raw.file_log "
            "WHERE source_id = %s "
            "ORDER BY started_at DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"No file_log entries for {source_id}")
            return 1

        batch_started_at = row[0]

        # Get all files in this batch
        cur.execute(
            "SELECT id, filename, row_count FROM raw.file_log "
            "WHERE source_id = %s AND started_at = %s "
            "ORDER BY filename",
            (source_id, batch_started_at),
        )
        files = cur.fetchall()

        if not files:
            print(f"No files found in batch for {source_id}")
            return 1

        # Get per-file rejection counts from the rejected view
        rej_view = f"rejected.rej_{source_id}"
        try:
            cur.execute(
                f"SELECT file_log_id, count(*) FROM {rej_view} GROUP BY file_log_id",  # noqa: S608
            )
            rej_counts = dict(cur.fetchall())
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            # No rejected view means no rejections possible
            rej_counts = {}

        store = FileStore(STORE_BASE)
        passed = 0
        failed = 0

        print(f"\nQuality gate for {source_id} (threshold: {threshold}%):")

        for file_log_id, filename, total_rows in files:
            if not filename:
                continue

            rejected_rows = rej_counts.get(file_log_id, 0)
            total = total_rows or 0

            if total == 0:
                pct = 100.0
            else:
                pct = (rejected_rows / total) * 100.0

            if pct <= threshold:
                status = "PASS"
                passed += 1
                store.move_file_to_done(source_id, filename)
            else:
                status = "FAIL"
                failed += 1
                reason = f"{rejected_rows}/{total} rows rejected ({pct:.1f}% > {threshold}%)"
                store.move_file_to_rejected(source_id, filename, reason)
                # Update file_log status to 'rejected'
                cur.execute(
                    "UPDATE raw.file_log SET status = 'rejected' WHERE id = %s",
                    (file_log_id,),
                )

            print(f"  {status}  {filename:<40} {rejected_rows}/{total} rejected ({pct:.1f}%)")

        conn.commit()

        total_files = passed + failed
        if total_files == 0:
            print("Result: NO FILES")
            return 1
        elif failed == 0:
            print(f"Result: ALL PASSED ({passed} of {total_files} files passed)")
            return 0
        elif passed == 0:
            print(f"Result: ALL FAILED ({failed} of {total_files} files failed)")
            return 1
        else:
            print(f"Result: PARTIAL ({passed} of {total_files} files passed)")
            return 2

    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Per-file quality gate")
    parser.add_argument("--source", required=True, help="Source ID to check")
    args = parser.parse_args()

    exit_code = quality_gate(args.source)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
