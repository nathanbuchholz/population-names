"""Download source data from a GitHub release asset.

The raw data files are not committed to the repo. Instead, they are packaged
as a tarball and attached to a GitHub release. This script downloads and
extracts the tarball to data/raw/, skipping the download if files already exist.

Usage:
    python scripts/download_sources.py [--force]
"""

import argparse
import logging
import subprocess
import sys
import tarfile
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

# GitHub release tag and asset name
RELEASE_TAG = "data-v1"
ASSET_NAME = "source-data.tar.gz"


def _get_download_url() -> str:
    """Build the release asset URL from git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Could not determine git remote. Set RELEASE_URL env var.")
        sys.exit(1)

    # Convert git@github.com:owner/repo.git or https://github.com/owner/repo.git
    if remote.startswith("git@"):
        remote = remote.replace("git@github.com:", "https://github.com/")
    remote = remote.removesuffix(".git")

    return f"{remote}/releases/download/{RELEASE_TAG}/{ASSET_NAME}"


def _is_populated() -> bool:
    """Check if data/raw/ already has files (cache hit)."""
    if not RAW_DIR.exists():
        return False
    files = [f for f in RAW_DIR.rglob("*") if f.is_file()]
    return len(files) > 10  # expect ~75 files


def download(force: bool = False) -> None:
    url = _get_download_url()

    if not force and _is_populated():
        count = sum(1 for f in RAW_DIR.rglob("*") if f.is_file())
        logger.info("CACHED: data/raw/ already has %d files, skipping download", count)
        return

    logger.info("Downloading %s ...", url)
    tarball = DATA_DIR / ASSET_NAME
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Try direct curl download first, fall back to gh CLI
    curl_ok = False
    try:
        subprocess.run(
            ["curl", "-fSL", "-o", str(tarball), url],
            check=True,
        )
        curl_ok = True
    except subprocess.CalledProcessError:
        pass

    if not curl_ok:
        try:
            subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    RELEASE_TAG,
                    "--pattern",
                    ASSET_NAME,
                    "--output",
                    str(tarball),
                    "--clobber",
                ],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Download failed. To set up data manually, see README.")
            sys.exit(1)

    logger.info("Extracting to data/ ...")
    with tarfile.open(tarball) as tar:
        tar.extractall(path=DATA_DIR, filter="data")

    tarball.unlink()

    count = sum(1 for f in RAW_DIR.rglob("*") if f.is_file())
    logger.info("DONE: %d files extracted to data/raw/", count)


def main():
    parser = argparse.ArgumentParser(description="Download source data from GitHub release")
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    download(force=args.force)


if __name__ == "__main__":
    main()
