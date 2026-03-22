"""Transforms for Republic of Ireland (CSO) data sources.

Handles PxStat 5-column CSV format:
  Statistic Label, Year, {Name Col}, UNIT, VALUE

Schema version provides:
  - name_column: which column holds the name (e.g. "Boys Names", "Surnames")
  - value_meaning: what VALUE represents ("count" or "rank")
  - sex: gender code for forename sources ("M" or "F")

Files have UTF-8 BOM. Empty VALUE means suppressed data (skip row).
"""

import csv as csv_mod
from pathlib import Path

from pipeline.transforms import register, resolve_schema_version, write_csv


def _read_pxstat_csv(filepath: Path) -> tuple[list[str], list[list[str]]]:
    """Read a PxStat CSV, handling BOM. Returns (headers, rows)."""
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv_mod.reader(f)
        headers = next(reader)
        headers = [h.strip() for h in headers]
        rows = [row for row in reader]
    return headers, rows


def _find_col(headers: list[str], name: str) -> int | None:
    """Find the index of a column by name."""
    for i, h in enumerate(headers):
        if h.strip() == name:
            return i
    return None


def _transform_cso_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """CSO forenames PxStat CSV: name_column and sex from schema version config."""
    results = []

    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".csv":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        name_col_name = version.get("name_column", "Boys Names")
        sex = version.get("sex", "M")

        headers, rows = _read_pxstat_csv(archived_file)

        year_idx = _find_col(headers, "Year")
        name_idx = _find_col(headers, name_col_name)
        value_idx = _find_col(headers, "VALUE")

        if year_idx is None or name_idx is None or value_idx is None:
            continue

        data_rows = []
        for row in rows:
            if len(row) <= max(year_idx, name_idx, value_idx):
                continue
            name = row[name_idx].strip()
            year_str = row[year_idx].strip()
            value_str = row[value_idx].strip()

            # Pass through all rows (including bad data) so the staging
            # rejected_rows view can catch and label them.
            try:
                count = int(value_str)
            except (ValueError, TypeError):
                count = value_str  # keep raw string for rejection detection

            data_rows.append([name, sex, count, "", year_str])

        out_path = converted_dir / archived_file.name
        results.append(write_csv(out_path, ["name", "sex", "count", "rank", "year"], data_rows))

    return results


@register("cso_forenames_boys")
def transform_cso_boys(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    return _transform_cso_forenames(archived_dir, converted_dir, cfg)


@register("cso_forenames_girls")
def transform_cso_girls(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    return _transform_cso_forenames(archived_dir, converted_dir, cfg)


@register("cso_surnames")
def transform_cso_surnames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """CSO surnames PxStat CSV: name_column and value_meaning from schema version config."""
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".csv":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        name_col_name = version.get("name_column", "Surnames")
        value_meaning = version.get("value_meaning", "rank")

        headers, rows = _read_pxstat_csv(archived_file)

        year_idx = _find_col(headers, "Year")
        name_idx = _find_col(headers, name_col_name)
        value_idx = _find_col(headers, "VALUE")

        if year_idx is None or name_idx is None or value_idx is None:
            continue

        data_rows = []
        for row in rows:
            if len(row) <= max(year_idx, name_idx, value_idx):
                continue
            name = row[name_idx].strip()
            year_str = row[year_idx].strip()
            value_str = row[value_idx].strip()

            # Pass through all rows (including bad data) so the staging
            # rejected_rows view can catch and label them.
            try:
                value = int(value_str)
            except (ValueError, TypeError):
                value = value_str  # keep raw string for rejection detection

            if value_meaning == "count":
                data_rows.append([name, value, "", year_str])
            else:
                # VALUE is rank, count not available
                data_rows.append([name, "", value, year_str])

        out_path = converted_dir / archived_file.name
        results.append(write_csv(out_path, ["name", "count", "rank", "year"], data_rows))

    return results
