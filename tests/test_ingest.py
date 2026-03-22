"""Integration tests for ingest.py (requires test DB with psycopg2)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ingest import ingest_source


@pytest.fixture
def pg_conn():
    """Sync psycopg2 connection to test DB, with raw schema setup/teardown."""
    url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://pipeline:pipeline@localhost:5432/population_names_test",
    )
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw.file_log (
            id              BIGSERIAL PRIMARY KEY,
            source_id       TEXT NOT NULL,
            filename        TEXT NOT NULL,
            file_hash       TEXT,
            file_size_bytes BIGINT,
            status          TEXT NOT NULL CHECK (status IN ('success', 'failed')),
            row_count       INTEGER,
            error_message   TEXT,
            forced          BOOLEAN NOT NULL DEFAULT FALSE,
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ
        )
    """)
    conn.commit()
    cur.close()
    yield conn
    # Teardown
    cur = conn.cursor()
    cur.execute("DELETE FROM raw.file_log")
    conn.commit()
    cur.close()
    conn.close()


def _create_test_table(conn, table="raw.test_source"):
    """Create a simple raw table for testing."""
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"""
        CREATE TABLE {table} (
            name TEXT,
            count TEXT,
            file_log_id BIGINT,
            _loaded_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()


def _drop_test_table(conn, table="raw.test_source"):
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    cur.close()


def _row_count(conn, table="raw.test_source"):
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    count = cur.fetchone()[0]
    cur.close()
    return count


def _log_rows(conn, source_id="test_source"):
    cur = conn.cursor()
    cur.execute(
        "SELECT status, row_count, forced, error_message, filename, file_hash "
        "FROM raw.file_log "
        "WHERE source_id = %s ORDER BY started_at, filename",
        (source_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


SOURCE_CFG = {
    "db": {
        "table": "raw.test_source",
        "columns": ["name", "count"],
    }
}


@pytest.fixture(autouse=True)
def _setup_test_table(pg_conn):
    _create_test_table(pg_conn)
    yield
    _drop_test_table(pg_conn)


def test_ingest_source_logs_success(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\nAlice,10\nBob,20\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")

    rows = _log_rows(pg_conn)
    assert len(rows) == 1
    status, row_count, forced, error_message, filename, file_hash = rows[0]
    assert status == "success"
    assert row_count == 2
    assert forced is False
    assert error_message is None
    assert filename == "data.csv"
    assert file_hash is not None
    assert _row_count(pg_conn) == 2


def test_ingest_source_skips_unchanged(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\nAlice,10\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")
        ingest_source(pg_conn, "test_source")

    rows = _log_rows(pg_conn)
    # No "skipped" row - skip means no DB write at all
    assert len(rows) == 1
    assert rows[0][0] == "success"
    # Data still present
    assert _row_count(pg_conn) == 1


def test_ingest_source_force_reprocesses(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\nAlice,10\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")
        ingest_source(pg_conn, "test_source", force=True)

    rows = _log_rows(pg_conn)
    assert len(rows) == 2
    assert rows[0][0] == "success"
    assert rows[1][0] == "success"
    assert rows[1][2] is True  # forced


def test_ingest_source_detects_changed_files(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    csv_file = csv_dir / "data.csv"
    csv_file.write_text("name,count\nAlice,10\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")

        csv_file.write_text("name,count\nAlice,10\nCharlie,30\n")
        ingest_source(pg_conn, "test_source")

    rows = _log_rows(pg_conn)
    assert len(rows) == 2
    assert rows[0][0] == "success"
    assert rows[1][0] == "success"
    assert _row_count(pg_conn) == 2


def test_ingest_source_logs_failure(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\nAlice,10\n")

    bad_cfg = {"db": {"table": "raw.nonexistent_table", "columns": ["name", "count"]}}

    with (
        patch("scripts.ingest.get_source", return_value=bad_cfg),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        with pytest.raises(Exception):
            ingest_source(pg_conn, "test_source")

    rows = _log_rows(pg_conn)
    assert len(rows) == 1
    assert rows[0][0] == "failed"
    assert rows[0][3] is not None  # error_message


def test_ingest_source_failure_doesnt_lose_data(pg_conn, tmp_path):
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    csv_file = csv_dir / "data.csv"
    csv_file.write_text("name,count\nAlice,10\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")
        assert _row_count(pg_conn) == 1

    # Now simulate a failure by pointing to a bad table for the second run.
    # Use force=True to bypass change detection (same files would be skipped).
    bad_cfg = {"db": {"table": "raw.nonexistent_table", "columns": ["name", "count"]}}
    with (
        patch("scripts.ingest.get_source", return_value=bad_cfg),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        with pytest.raises(Exception):
            ingest_source(pg_conn, "test_source", force=True)

    # Original data still intact (rollback worked)
    assert _row_count(pg_conn) == 1


def test_ingest_source_file_log_id_populated(pg_conn, tmp_path):
    """Verify that file_log_id is populated in raw table rows."""
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\nAlice,10\n")

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        ingest_source(pg_conn, "test_source")

    cur = pg_conn.cursor()
    cur.execute("SELECT file_log_id FROM raw.test_source")
    file_log_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    assert all(fid is not None for fid in file_log_ids)


def test_ingest_source_zero_rows_rolls_back(pg_conn, tmp_path):
    """CSV with header-only (0 data rows) raises RuntimeError and rolls back."""
    csv_dir = tmp_path / "test_source"
    csv_dir.mkdir()
    (csv_dir / "data.csv").write_text("name,count\n")  # header only, no data

    with (
        patch("scripts.ingest.get_source", return_value=SOURCE_CFG),
        patch("scripts.ingest.DATA_DIR", str(tmp_path)),
    ):
        with pytest.raises(RuntimeError, match="ingested 0 rows"):
            ingest_source(pg_conn, "test_source")

    # Table should be empty (rolled back)
    assert _row_count(pg_conn) == 0

    # Failure should be logged
    rows = _log_rows(pg_conn)
    assert len(rows) == 1
    assert rows[0][0] == "failed"
