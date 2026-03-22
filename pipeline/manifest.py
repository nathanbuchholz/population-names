"""Load and query the source manifest (pipeline/sources.yml)."""

from pathlib import Path

import yaml

_MANIFEST_PATH = Path(__file__).parent / "sources.yml"
_cache: dict | None = None


def load_manifest(path: str | Path | None = None) -> dict:
    """Load the YAML source manifest and return the full dict."""
    global _cache
    if _cache is not None and path is None:
        return _cache
    p = Path(path) if path else _MANIFEST_PATH
    with open(p) as f:
        data = yaml.safe_load(f)
    if path is None:
        _cache = data
    return data


def get_source(source_id: str, path: str | Path | None = None) -> dict:
    """Return config dict for a single source, or raise KeyError."""
    manifest = load_manifest(path)
    sources = manifest["sources"]
    if source_id not in sources:
        raise KeyError(f"Unknown source: {source_id!r}. Available: {list(sources)}")
    return sources[source_id]


def list_sources(path: str | Path | None = None) -> list[str]:
    """Return list of all registered source IDs."""
    manifest = load_manifest(path)
    return list(manifest["sources"].keys())
