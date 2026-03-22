"""Data contract tests: validate API models match MV definitions in refresh_views.sql.

These are unit tests (no database needed) that parse the SQL file and compare
column names against SQLAlchemy models and Pydantic schemas.
"""

import re
from pathlib import Path

import pytest

from src.db.models import Forename, MvForenameRanking, MvSurnameRanking, Surname
from src.schemas.analytics import RankedForenameItem, RankedSurnameItem
from src.schemas.names import ForenameItem, SurnameItem

SQL_PATH = Path(__file__).resolve().parent.parent / "scripts" / "refresh_views.sql"


def _parse_mv_columns(sql_text: str) -> dict[str, set[str]]:
    """Extract column names from CREATE MATERIALIZED VIEW statements.

    Returns a dict mapping table name to set of column names.
    Handles aliased columns (e.g. ``sum(count) AS count`` -> ``count``)
    and qualified columns (e.g. ``f.name`` -> ``name``).
    """
    results = {}
    # Match each CREATE MATERIALIZED VIEW ... AS <select> up to the next semicolon
    pattern = re.compile(
        r"CREATE MATERIALIZED VIEW\s+(?:IF NOT EXISTS\s+)?public\.(\w+)\s+AS\s+"
        r"(?:WITH\s+\w+\s+AS\s*\(.*?\)\s*)?"  # optional CTE
        r"SELECT\s+(.*?)\s+FROM\s",
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(sql_text):
        table_name = match.group(1)
        select_clause = match.group(2)

        columns = set()
        # Split on commas that are not inside parentheses
        parts = _split_select(select_clause)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Check for AS alias (the canonical column name)
            as_match = re.search(r"\bAS\s+(\w+)\s*$", part, re.IGNORECASE)
            if as_match:
                columns.add(as_match.group(1))
            else:
                # Take the last identifier (handles "f.name" -> "name")
                ident_match = re.search(r"(\w+)\s*$", part)
                if ident_match:
                    columns.add(ident_match.group(1))
        results[table_name] = columns

    return results


def _split_select(clause: str) -> list[str]:
    """Split a SELECT clause on top-level commas (not inside parentheses)."""
    parts = []
    depth = 0
    current = []
    for ch in clause:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


@pytest.fixture(scope="module")
def mv_columns():
    sql_text = SQL_PATH.read_text()
    return _parse_mv_columns(sql_text)


# -- SQLAlchemy model vs MV column tests --


class TestSQLAlchemyModelsMatchMV:
    def _assert_cols(self, actual, expected, label):
        extra = actual - expected
        missing = expected - actual
        assert actual == expected, f"{label} drift: extra={extra}, missing={missing}"

    def test_forenames_columns(self, mv_columns):
        expected = mv_columns["forenames"]
        actual = {c.name for c in Forename.__table__.columns}
        self._assert_cols(actual, expected, "Forename")

    def test_surnames_columns(self, mv_columns):
        expected = mv_columns["surnames"]
        actual = {c.name for c in Surname.__table__.columns}
        self._assert_cols(actual, expected, "Surname")

    def test_mv_forename_rankings_columns(self, mv_columns):
        expected = mv_columns["mv_forename_rankings"]
        actual = {c.name for c in MvForenameRanking.__table__.columns}
        self._assert_cols(actual, expected, "MvForenameRanking")

    def test_mv_surname_rankings_columns(self, mv_columns):
        expected = mv_columns["mv_surname_rankings"]
        actual = {c.name for c in MvSurnameRanking.__table__.columns}
        self._assert_cols(actual, expected, "MvSurnameRanking")


# -- Pydantic schema vs API query column tests --
# The API queries join dimension tables, so response schemas use
# resolved names (gender_code instead of gender_id, etc).


class TestPydanticSchemasMatchAPIQueries:
    """Validate Pydantic response schemas cover all API fields."""

    def _assert_fields(self, schema, expected, label):
        actual = set(schema.model_fields.keys())
        extra = actual - expected
        missing = expected - actual
        assert actual == expected, f"{label} drift: extra={extra}, missing={missing}"

    def test_forename_item_fields(self):
        expected = {
            "name",
            "gender_code",
            "country_name",
            "year",
            "count",
        }
        self._assert_fields(ForenameItem, expected, "ForenameItem")

    def test_surname_item_fields(self):
        expected = {"name", "country_name", "year", "count"}
        self._assert_fields(SurnameItem, expected, "SurnameItem")

    def test_ranked_forename_item_fields(self):
        expected = {
            "name",
            "gender_code",
            "country_name",
            "year",
            "count",
            "rank",
            "pct_of_year_total",
        }
        self._assert_fields(
            RankedForenameItem,
            expected,
            "RankedForenameItem",
        )

    def test_ranked_surname_item_fields(self):
        expected = {
            "name",
            "country_name",
            "year",
            "count",
            "rank",
            "pct_of_year_total",
        }
        self._assert_fields(
            RankedSurnameItem,
            expected,
            "RankedSurnameItem",
        )


class TestSQLParsing:
    """Sanity-check that the SQL parser finds all expected MVs."""

    def test_all_mvs_found(self, mv_columns):
        expected_tables = {"forenames", "surnames", "mv_forename_rankings", "mv_surname_rankings"}
        assert set(mv_columns.keys()) == expected_tables
