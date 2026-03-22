"""Transforms for Scotland (NRS) data sources."""

import csv as csv_mod
from pathlib import Path

from pipeline.transforms import read_xlsx_rows, register, resolve_schema_version, write_csv


@register("nrs_forenames")
def transform_nrs_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """CSV with header from schema version column_map (Year,Sex,Name,Number,Rank)."""
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".csv":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        col_map = version.get(
            "column_map",
            {
                "name": "Name",
                "sex": "Sex",
                "count": "Number",
                "rank": "Rank",
                "year": "Year",
            },
        )

        with open(archived_file, encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            data_rows = []
            for row in reader:
                sex_raw = row.get(col_map["sex"], "").strip()
                sex = "M" if sex_raw.lower().startswith("b") else "F"
                data_rows.append(
                    [
                        row[col_map["name"]].strip(),
                        sex,
                        int(row[col_map["count"]]),
                        int(row[col_map["rank"]]),
                        int(row[col_map["year"]]),
                    ]
                )

        out_path = converted_dir / archived_file.name
        results.append(write_csv(out_path, ["name", "sex", "count", "rank", "year"], data_rows))

    return results


@register("nrs_surnames")
def transform_nrs_surnames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """XLSX with sheet name and skip_rows from schema version config."""
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".xlsx":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        sheet_name = version.get("sheet_name", "Surnames TimeSeries 1975to2024")
        skip_rows = version.get("skip_rows", 3)

        rows = read_xlsx_rows(archived_file, sheet_name, skip_rows=skip_rows)
        if not rows:
            continue

        # First row is header: (Year, Surname, Number, Rank)
        data_rows = []
        for row in rows[1:]:
            year, surname, number, rank = row[0], row[1], row[2], row[3]
            if surname is None or number is None:
                continue
            data_rows.append([surname, int(number), int(rank), int(year)])

        out_path = converted_dir / (archived_file.stem + ".csv")
        results.append(write_csv(out_path, ["name", "count", "rank", "year"], data_rows))

    return results
