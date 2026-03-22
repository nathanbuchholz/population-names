"""Scraper for Irish-origin surnames from Wikipedia.

Combines two Wikipedia category pages:
  1. Category:Anglicised_Irish-language_surnames (~449 names)
  2. Category:Surnames_of_Irish_origin (~720 names)

Used as a proxy for Northern Ireland surnames since no official NI surname
dataset exists with a clear license. Both categories are CC BY-SA.

Usage:
  python scripts/scrapers/scrape_ni_surnames.py --output-dir data/archived/ni_surnames
  python scripts/scrapers/scrape_ni_surnames.py --output-dir /tmp/test --dry-run
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

CATEGORIES = [
    {
        "url": "https://en.wikipedia.org/wiki/Category:Anglicised_Irish-language_surnames",
        "tag": "anglicised",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Category:Surnames_of_Irish_origin",
        "tag": "irish_origin",
    },
]


def _is_meta_entry(name: str) -> bool:
    """Detect Wikipedia meta/list entries that aren't actual surnames."""
    lower = name.lower()
    return lower.startswith(("list of ", "clan ", "category:"))


def _clean_wiki_name(name: str) -> str:
    """Decode HTML entities and remove parenthetical suffixes."""
    name = html.unescape(name)
    return re.sub(r"\s*\(.*?\)\s*$", "", name).strip()


def _parse_category_page(html: str) -> list[str]:
    """Extract surname links from a Wikipedia category page."""
    cat_match = re.search(r'<div id="mw-pages".*?</div>\s*</div>\s*</div>', html, re.DOTALL)
    if not cat_match:
        return []
    return re.findall(r"<li><a[^>]*>([^<]+)</a>", cat_match.group())


def _get_next_page_url(html: str, base_url: str) -> str | None:
    """Find the 'next page' link in a Wikipedia category page."""
    match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>next page</a>', html)
    if not match:
        return None
    href = match.group(1).replace("&amp;", "&")
    if href.startswith("/"):
        return "https://en.wikipedia.org" + href
    return href


def fetch_category(client: httpx.Client, url: str) -> list[str]:
    """Fetch all pages of a Wikipedia category and return raw name strings."""
    all_names = []
    current_url = url

    while current_url:
        resp = client.get(current_url)
        resp.raise_for_status()
        names = _parse_category_page(resp.text)
        all_names.extend(names)
        logger.debug(f"  Fetched {len(names)} names from {current_url}")
        current_url = _get_next_page_url(resp.text, url)

    return all_names


def scrape(output_dir: Path, dry_run: bool = False) -> Path:
    """Scrape both Wikipedia categories and write combined CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "ni_surnames.csv"

    if dry_run:
        logger.debug("[dry-run] Would fetch from:")
        for cat in CATEGORIES:
            logger.debug(f"[dry-run]   {cat['url']}")
        logger.debug(f"[dry-run] Would write to {output_file}")
        return output_file

    seen: dict[str, dict] = {}  # uppercase name -> {name, origin}
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
        for cat in CATEGORIES:
            logger.info(f"Fetching {cat['tag']} from {cat['url']}...")
            raw_names = fetch_category(client, cat["url"])
            logger.info(f"  -> {len(raw_names)} raw entries")

            for raw_name in raw_names:
                name = _clean_wiki_name(raw_name)
                if not name or _is_meta_entry(name) or name.lower() in ("irish surnames",):
                    continue
                key = name.upper()
                if key in seen:
                    existing = seen[key]
                    if cat["tag"] not in existing["origin"].split(","):
                        existing["origin"] += "," + cat["tag"]
                else:
                    seen[key] = {"name": name, "origin": cat["tag"]}

    rows = [entry for _, entry in sorted(seen.items())]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "origin"])
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Wrote {len(rows)} rows to {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Scrape Irish-origin surnames from Wikipedia")
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
