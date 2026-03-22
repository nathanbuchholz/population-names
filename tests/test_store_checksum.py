"""Unit tests for compute_file_manifest and compute_composite_hash."""

from pipeline.store import compute_composite_hash, compute_file_manifest


def test_compute_file_manifest_returns_sorted_entries(tmp_path):
    (tmp_path / "c.csv").write_text("name,count\nAlice,10\n")
    (tmp_path / "a.csv").write_text("name,count\nBob,20\n")
    (tmp_path / "b.csv").write_text("name,count\nCharlie,30\n")

    manifest = compute_file_manifest(tmp_path)

    assert len(manifest) == 3
    assert [m["filename"] for m in manifest] == ["a.csv", "b.csv", "c.csv"]
    for m in manifest:
        assert len(m["sha256"]) == 64
        assert m["size_bytes"] > 0


def test_compute_file_manifest_empty_directory(tmp_path):
    assert compute_file_manifest(tmp_path) == []


def test_compute_file_manifest_skips_non_csv(tmp_path):
    (tmp_path / "data.csv").write_text("name\nAlice\n")
    (tmp_path / "meta.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("hello")

    manifest = compute_file_manifest(tmp_path)
    assert len(manifest) == 1
    assert manifest[0]["filename"] == "data.csv"


def test_compute_composite_hash_deterministic(tmp_path):
    (tmp_path / "a.csv").write_text("name\nAlice\n")
    (tmp_path / "b.csv").write_text("name\nBob\n")

    m1 = compute_file_manifest(tmp_path)
    m2 = compute_file_manifest(tmp_path)

    assert compute_composite_hash(m1) == compute_composite_hash(m2)


def test_compute_composite_hash_changes_on_content_change(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("name\nAlice\n")
    hash1 = compute_composite_hash(compute_file_manifest(tmp_path))

    f.write_text("name\nBob\n")
    hash2 = compute_composite_hash(compute_file_manifest(tmp_path))

    assert hash1 != hash2


def test_compute_composite_hash_empty_manifest():
    assert compute_composite_hash([]) == ""
