"""CLI for file store operations (retrieve, promote, status)."""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path so pipeline package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.manifest import get_source, list_sources  # noqa: E402
from pipeline.store import FileStore  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def cmd_status(store: FileStore, _args):
    """Print tier status for all sources."""
    st = store.status()
    logger.info(f"{'Source':<20} {'Archived':>12} {'Converted':>12} {'Validated':>12}")
    logger.info("-" * 58)
    for sid, tiers in st.items():

        def fmt(tier):
            fc = tier["file_count"]
            tb = tier["total_bytes"]
            if fc == 0:
                return "-"
            return f"{fc}f / {tb // 1024}KB"

        b, s, g = fmt(tiers["archived"]), fmt(tiers["converted"]), fmt(tiers["validated"])
        logger.info(f"{sid:<20} {b:>12} {s:>12} {g:>12}")


def _parse_raw_entry(entry):
    """Parse a store.files entry into (raw_path, archived_name)."""
    if isinstance(entry, str):
        return entry, Path(entry).name
    return entry["origin_path"], entry.get("archived_name", Path(entry["origin_path"]).name)


def cmd_retrieve(store: FileStore, args):
    """Retrieve raw files to archived tier."""
    sources = list_sources() if args.all else [args.source]
    for sid in sources:
        if args.dry_run:
            cfg = get_source(sid)
            store_files = cfg.get("store", {}).get("files", [])
            if not store_files:
                logger.debug(f"{sid}: no store.files defined, would skip")
                continue
            for entry in store_files:
                raw_path, archived_name = _parse_raw_entry(entry)
                src = store.raw_dir / raw_path
                exists = src.exists()
                status = "exists" if exists else "MISSING"
                logger.debug(f"  Would copy {src} -> archived/{sid}/{archived_name}  [{status}]")
            continue
        logger.info(f"Retrieving {sid}...")
        files = store.retrieve(sid)
        logger.debug(f"  -> {len(files)} file(s) to archived")


def cmd_promote(store: FileStore, args):
    """Promote files through tiers."""
    sources = list_sources() if args.all else [args.source]
    tier = getattr(args, "tier", None)

    for sid in sources:
        if args.dry_run:
            archived_dir = store.archived_dir / sid
            converted_dir = store.converted_dir / sid
            if (tier is None or tier == "converted") and archived_dir.exists():
                files = [f for f in archived_dir.iterdir() if not f.name.endswith(".json")]
                for f in sorted(files):
                    logger.debug(f"  Would promote {f.name} to converted/{sid}/")
            if (tier is None or tier == "validated") and converted_dir.exists():
                files = [f for f in converted_dir.iterdir() if not f.name.endswith(".json")]
                for f in sorted(files):
                    logger.debug(f"  Would promote {f.name} to validated/{sid}/")
            if not archived_dir.exists() and not converted_dir.exists():
                logger.debug(f"  {sid}: no archived/converted data found")
            continue

        if tier is None or tier == "converted":
            logger.info(f"Promoting {sid} to converted...")
            files = store.promote_to_converted(sid)
            logger.debug(f"  -> {len(files)} file(s) in converted")

        if tier is None or tier == "validated":
            logger.info(f"Promoting {sid} to validated...")
            files = store.promote_to_validated(sid)
            logger.debug(f"  -> {len(files)} file(s) in validated")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="File store CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show tier status for all sources")

    p_retrieve = sub.add_parser("retrieve", help="Copy raw files to archived tier")
    p_retrieve.add_argument("--all", action="store_true", help="Retrieve all sources")
    p_retrieve.add_argument("--source", help="Single source to retrieve")
    p_retrieve.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without executing",
    )

    p_promote = sub.add_parser("promote", help="Promote through converted/validated tiers")
    p_promote.add_argument("--all", action="store_true", help="Promote all sources")
    p_promote.add_argument("--source", help="Single source to promote")
    p_promote.add_argument(
        "--tier",
        choices=["converted", "validated"],
        help="Stop at specific tier",
    )
    p_promote.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without executing",
    )

    args = parser.parse_args()

    if args.command in ("retrieve", "promote"):
        if not args.all and not args.source:
            parser.error("Specify --source=NAME or --all")

    store = FileStore(DATA_DIR)

    cmds = {"status": cmd_status, "retrieve": cmd_retrieve, "promote": cmd_promote}
    cmds[args.command](store, args)


if __name__ == "__main__":
    main()
