"""Transforms for Northern Ireland (NISRA) data sources."""

import re
from pathlib import Path

from pipeline.transforms import read_xlsx_rows, register, resolve_schema_version, write_csv


@register("nisra_forenames")
def transform_nisra_forenames(archived_dir: Path, converted_dir: Path, cfg: dict) -> list[Path]:
    """XLSX with sheets and skip_rows from schema version config.

    Schema version provides:
      - sheets: list of {sheet_name, sex} pairs
      - skip_rows: metadata rows to skip

    Years laid out horizontally, each year = 3 columns:
    "{YYYY} Name", "Number of Babies", "Rank".
    Unpivot into long format: name, sex, count, rank, year.
    """
    results = []
    for archived_file in sorted(archived_dir.iterdir()):
        if archived_file.suffix != ".xlsx":
            continue

        version = resolve_schema_version(archived_file.name, cfg)
        sheets = version.get(
            "sheets",
            [
                {"sheet_name": "Table 1", "sex": "M"},
                {"sheet_name": "Table 2", "sex": "F"},
            ],
        )
        skip_rows = version.get("skip_rows", 4)

        all_rows = []
        for sheet_cfg in sheets:
            sheet_name = sheet_cfg["sheet_name"]
            sex = sheet_cfg["sex"]
            rows = read_xlsx_rows(archived_file, sheet_name, skip_rows=skip_rows)
            if not rows:
                continue

            # Parse years from header row
            header = rows[0]
            years = []
            for i in range(0, len(header), 3):
                cell = str(header[i]) if header[i] else ""
                match = re.match(r"(\d{4})", cell)
                if match:
                    years.append((i, int(match.group(1))))

            # Unpivot data rows
            for row in rows[1:]:
                for col_offset, year in years:
                    name = row[col_offset] if col_offset < len(row) else None
                    count = row[col_offset + 1] if col_offset + 1 < len(row) else None
                    rank = row[col_offset + 2] if col_offset + 2 < len(row) else None
                    if name is None or count is None:
                        continue
                    # Skip suppressed values (".." means count < 3)
                    if str(count).strip() in ("", "-", ".."):
                        continue
                    try:
                        count_int = int(count)
                        rank_str = str(rank).strip() if rank else ""
                        rank_val = int(rank) if rank_str not in ("", "-", "..") else None
                    except (ValueError, TypeError):
                        continue
                    all_rows.append([str(name).strip(), sex, count_int, rank_val, year])

        if all_rows:
            out_path = converted_dir / (archived_file.stem + ".csv")
            results.append(write_csv(out_path, ["name", "sex", "count", "rank", "year"], all_rows))

    return results
