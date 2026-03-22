"""Tests for FileStore lifecycle (no database needed)."""

import json
from unittest.mock import patch

import pytest

from pipeline.store import FileStore


def _mock_manifest():
    return {
        "sources": {
            "test_source": {
                "store": {
                    "file_pattern": "test_source/*.csv",
                    "validated_columns": [
                        {"target": "name"},
                        {"target": "count"},
                    ],
                },
                "quality": {},
            },
        },
    }


def _mock_get_source(source_id, path=None):
    return _mock_manifest()["sources"][source_id]


@pytest.fixture
def store(tmp_path):
    with (
        patch("pipeline.store.load_manifest", return_value=_mock_manifest()),
        patch("pipeline.store.get_source", side_effect=_mock_get_source),
        patch("pipeline.store.list_sources", return_value=["test_source"]),
    ):
        yield FileStore(tmp_path)


class TestRetrievePattern:
    def test_copies_matching_files(self, store, tmp_path):
        raw_dir = tmp_path / "raw" / "test_source"
        raw_dir.mkdir(parents=True)
        (raw_dir / "data1.csv").write_text("name,count\nAlice,10\n")
        (raw_dir / "data2.csv").write_text("name,count\nBob,20\n")

        results = store.retrieve("test_source")
        assert len(results) == 2

        archived_dir = tmp_path / "archived" / "test_source"
        assert (archived_dir / "data1.csv").exists()
        assert (archived_dir / "data2.csv").exists()
        # Metadata JSON created
        assert (archived_dir / "data1.csv.meta.json").exists()

    def test_no_match(self, store, tmp_path):
        # raw dir exists but no matching files
        raw_dir = tmp_path / "raw" / "test_source"
        raw_dir.mkdir(parents=True)

        results = store.retrieve("test_source")
        assert results == []


class TestPromoteToConverted:
    def test_with_transform(self, store, tmp_path):
        archived_dir = tmp_path / "archived" / "test_source"
        archived_dir.mkdir(parents=True)
        (archived_dir / "data.csv").write_text("name,count\nAlice,10\n")

        converted_path = tmp_path / "converted" / "test_source" / "output.csv"

        def mock_transform(a_dir, c_dir, cfg):
            out = c_dir / "output.csv"
            out.write_text("name,count\nAlice,10\n")
            return [out]

        with patch("pipeline.store.get_transform", return_value=mock_transform):
            results = store.promote_to_converted("test_source")
        assert len(results) == 1
        assert converted_path.exists()

    def test_generic_csv(self, store, tmp_path):
        archived_dir = tmp_path / "archived" / "test_source"
        archived_dir.mkdir(parents=True)
        (archived_dir / "data.csv").write_text("name,count\nAlice,10\n")

        with patch("pipeline.store.get_transform", return_value=None):
            results = store.promote_to_converted("test_source")
        assert len(results) == 1
        assert (tmp_path / "converted" / "test_source" / "data.csv").exists()


class TestPromoteToValidated:
    def test_basic(self, store, tmp_path):
        converted_dir = tmp_path / "converted" / "test_source"
        converted_dir.mkdir(parents=True)
        (converted_dir / "data.csv").write_text("name,count\nAlice,10\n")

        results = store.promote_to_validated("test_source")
        assert len(results) == 1
        assert (tmp_path / "validated" / "test_source" / "data.csv").exists()

    def test_skips_empty(self, store, tmp_path):
        converted_dir = tmp_path / "converted" / "test_source"
        converted_dir.mkdir(parents=True)
        (converted_dir / "empty.csv").write_text("")

        results = store.promote_to_validated("test_source")
        assert results == []

    def test_schema_rejection(self, tmp_path):
        manifest = {
            "sources": {
                "strict_src": {
                    "store": {"validated_columns": []},
                    "quality": {"expected_columns": ["name", "count"]},
                },
            },
        }

        def get_src(sid, path=None):
            return manifest["sources"][sid]

        with (
            patch("pipeline.store.load_manifest", return_value=manifest),
            patch("pipeline.store.get_source", side_effect=get_src),
            patch("pipeline.store.list_sources", return_value=["strict_src"]),
        ):
            fs = FileStore(tmp_path)

            # Create archived file with wrong columns
            archived_dir = tmp_path / "archived" / "strict_src"
            archived_dir.mkdir(parents=True)
            (archived_dir / "bad.csv").write_text("wrong,columns\nfoo,bar\n")

            # Create converted file (same stem)
            converted_dir = tmp_path / "converted" / "strict_src"
            converted_dir.mkdir(parents=True)
            (converted_dir / "bad.csv").write_text("wrong,columns\nfoo,bar\n")

            results = fs.promote_to_validated("strict_src")
            assert results == []

            # File should be in rejected/
            assert (tmp_path / "rejected" / "strict_src" / "bad.csv").exists()
            assert (tmp_path / "rejected" / "strict_src" / "bad.csv.rejection.json").exists()


class TestMoveFileToDone:
    def test_moves_file(self, store, tmp_path):
        archived_dir = tmp_path / "archived" / "test_source"
        archived_dir.mkdir(parents=True)
        (archived_dir / "data.csv").write_text("content")

        store.move_file_to_done("test_source", "data.csv")

        assert not (archived_dir / "data.csv").exists()
        assert (tmp_path / "done" / "test_source" / "data.csv").exists()


class TestMoveFileToRejected:
    def test_moves_with_log(self, store, tmp_path):
        archived_dir = tmp_path / "archived" / "test_source"
        archived_dir.mkdir(parents=True)
        (archived_dir / "data.csv").write_text("content")

        store.move_file_to_rejected("test_source", "data.csv", "bad data")

        assert not (archived_dir / "data.csv").exists()
        reject_dir = tmp_path / "rejected" / "test_source"
        assert (reject_dir / "data.csv").exists()
        assert (reject_dir / "data.csv.rejection.json").exists()

        log = json.loads((reject_dir / "data.csv.rejection.json").read_text())
        assert log["reason"] == "bad data"


class TestStatus:
    def test_returns_tier_counts(self, store, tmp_path):
        archived_dir = tmp_path / "archived" / "test_source"
        archived_dir.mkdir(parents=True)
        (archived_dir / "a.csv").write_text("data")
        (archived_dir / "b.csv").write_text("data")

        result = store.status()
        assert result["test_source"]["archived"]["file_count"] == 2
        assert result["test_source"]["converted"]["file_count"] == 0
