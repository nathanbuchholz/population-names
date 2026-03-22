"""Transforms for United States data sources."""

import csv as csv_mod
import re
from pathlib import Path

from pipeline.transforms import register, resolve_schema_version, write_csv


@register("ssa_forenames")
def transform_ssa_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """Individual yob{YYYY}.txt files. No header. Format: name,sex,count.

    Year is extracted from the filename via filename_date_re.
    """
    all_rows = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".txt":
            continue

        resolve_schema_version(archived_file.name, cfg)

        # Extract year from filename
        year_match = re.search(r"yob(\d{4})", archived_file.name)
        if not year_match:
            continue
        year = int(year_match.group(1))

        with open(archived_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                all_rows.append([parts[0], parts[1], int(parts[2]), year])

    results = []
    if all_rows:
        out_path = converted_dir / "ssa_forenames.csv"
        results.append(write_csv(out_path, ["name", "sex", "count", "year"], all_rows))
    return results


@register("census_surnames")
def transform_census_surnames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """CSV with proper headers (name, rank, count, ...).

    Schema version provides:
      - column_map: mapping of output columns to source columns
      - default_year: year to assign (source has no year column)
    """
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".csv":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        col_map = version.get("column_map", {"name": "name", "count": "count"})
        default_year = version.get("default_year", 2010)

        with open(archived_file, encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            data_rows = []
            for row in reader:
                raw_name = row.get(col_map["name"], "").strip()
                raw_count = row.get(col_map["count"], "").strip()
                if not raw_name or not raw_count:
                    continue
                data_rows.append([raw_name.title(), int(raw_count), default_year])

        out_path = converted_dir / archived_file.name
        results.append(write_csv(out_path, ["name", "count", "year"], data_rows))

    return results
