"""Scraper for Wales surnames from Wikipedia and Wiktionary.

Combines two sources:
  1. Wikipedia "Category:Surnames of Welsh origin" - ~80 surnames of Welsh origin
  2. Wiktionary "Appendix:English surnames (England and Wales)" - top 250 surnames
     in England & Wales by frequency (2002 data)

The Wiktionary source covers England AND Wales jointly; it is not Wales-specific.
Welsh-origin surnames from Wikipedia are tagged with origin='welsh'.

Usage:
  python scripts/scrapers/scrape_wales_surnames.py --output-dir data/archived/wales_surnames
  python scripts/scrapers/scrape_wales_surnames.py --output-dir /tmp/test --dry-run
"""

import argparse
import csv
import html
import logging
import re
import sys
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Category:Surnames_of_Welsh_origin"
WIKTIONARY_URL = "https://en.wiktionary.org/wiki/Appendix:English_surnames_(England_and_Wales)"


def _clean_wiki_name(name: str) -> str:
    """Decode HTML entities and remove parenthetical suffixes."""
    name = html.unescape(name)
    return re.sub(r"\s*\(.*?\)\s*$", "", name).strip()


def fetch_welsh_origin_surnames(client: httpx.Client) -> list[dict]:
    """Scrape Welsh-origin surnames from Wikipedia category page."""
    resp = client.get(WIKIPEDIA_URL)
    resp.raise_for_status()

    # Surnames are listed inside <div id="mw-pages"> as <li><a>Name</a></li>
    cat_match = re.search(r'<div id="mw-pages".*?</div>\s*</div>\s*</div>', resp.text, re.DOTALL)
    if not cat_match:
        logger.warning("Could not find mw-pages div on Wikipedia page")
        return []

    links = re.findall(r"<li><a[^>]*>([^<]+)</a>", cat_match.group())
    rows = []
    for raw_name in links:
        name = _clean_wiki_name(raw_name)
        # Skip meta entries
        if name.lower() in ("welsh surnames",):
            continue
        rows.append({"name": name, "rank": None, "count": None, "origin": "welsh"})

    return rows


def fetch_wiktionary_surnames(client: httpx.Client) -> list[dict]:
    """Scrape top-250 England & Wales surnames from Wiktionary appendix."""
    resp = client.get(WIKTIONARY_URL)
    resp.raise_for_status()

    # Entries are: <dd>RANK. <a ...>NAME</a> COUNT</dd>
    pattern = re.compile(r"<dd>(\d+)\.\s*<a[^>]*>([^<]+)</a>\s*([\d,]*)")
    rows = []
    for m in pattern.finditer(resp.text):
        rank = int(m.group(1))
        name = m.group(2).strip()
        count_str = m.group(3).replace(",", "").strip()
        count = int(count_str) if count_str else None
        rows.append({"name": name, "rank": rank, "count": count, "origin": "eaw_top250"})

    return rows


def scrape(output_dir: Path, dry_run: bool = False) -> Path:
    """Scrape both sources and write combined CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "wales_surnames.csv"

    if dry_run:
        logger.debug("[dry-run] Would fetch from:")
        logger.debug(f"[dry-run]   {WIKIPEDIA_URL}")
        logger.debug(f"[dry-run]   {WIKTIONARY_URL}")
        logger.debug(f"[dry-run] Would write to {output_file}")
        return output_file

    all_rows: list[dict] = []
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "api-demo-pipeline/1.0 "
                "(https://github.com/example/api-demo; educational project) "
                "httpx/0.27"
            ),
        },
    ) as client:
        logger.info("Fetching Welsh-origin surnames from Wikipedia...")
        welsh = fetch_welsh_origin_surnames(client)
        logger.debug(f"  -> {len(welsh)} surnames")
        all_rows.extend(welsh)

        logger.info("Fetching England & Wales top 250 from Wiktionary...")
        eaw = fetch_wiktionary_surnames(client)
        logger.debug(f"  -> {len(eaw)} surnames")
        all_rows.extend(eaw)

    # Deduplicate: if a name appears in both, keep the Wiktionary entry (has rank/count)
    # and merge the 'welsh' origin tag
    seen: dict[str, dict] = {}
    for row in all_rows:
        key = row["name"].upper()
        if key in seen:
            existing = seen[key]
            if row["origin"] == "welsh":
                existing["origin"] = (
                    "welsh,eaw_top250"
                    if existing["origin"] == "eaw_top250"
                    else existing["origin"]
                )
            elif existing["origin"] == "welsh":
                row["origin"] = "welsh,eaw_top250"
                seen[key] = row
        else:
            seen[key] = row

    deduped = list(seen.values())

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "rank", "count", "origin"])
        writer.writeheader()
        writer.writerows(deduped)

    logger.info(f"Wrote {len(deduped)} rows to {output_file} ({len(all_rows)} before dedup)")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Wales/England & Wales surnames from Wikipedia + Wiktionary"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory (archived path)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print URLs without fetching")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        scrape(args.output_dir, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
