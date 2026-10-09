"""Reserving and writing the artifact file (model_effort.artifact_store)."""

from __future__ import annotations

import pytest
from _model_effort_support import RUN_ID, _store_with_failing_replace
from model_effort import artifact_store
from model_effort.errors import UsageError


class TestArtifactStore:
    def test_reservation_creates_an_empty_placeholder(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        assert path == tmp_path / f"{RUN_ID}.json"
        assert path.read_text(encoding="utf-8") == ""

    def test_reserving_an_existing_artifact_is_refused_and_leaves_it_unchanged(
        self, tmp_path
    ):
        existing = tmp_path / f"{RUN_ID}.json"
        existing.write_text("sentinel", encoding="utf-8")

        with pytest.raises(UsageError) as excinfo:
            artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        assert "already exists" in str(excinfo.value)
        assert existing.read_text(encoding="utf-8") == "sentinel"

    def test_reserving_in_a_missing_directory_is_refused(self, tmp_path):
        with pytest.raises(UsageError) as excinfo:
            artifact_store.reserve_artifact_path(tmp_path / "nope", RUN_ID)

        assert "runs directory" in str(excinfo.value)

    def test_write_replaces_the_placeholder_with_the_full_text(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        artifact_store.write_artifact(path, '{"a": 1}\n')

        assert path.read_text(encoding="utf-8") == '{"a": 1}\n'
        assert [p.name for p in tmp_path.iterdir()] == [path.name]

    def test_failed_write_leaves_the_destination_untouched_and_no_temp_file(
        self, tmp_path, monkeypatch
    ):
        path = tmp_path / "a.json"
        path.write_text("original", encoding="utf-8")
        _store_with_failing_replace(monkeypatch)

        with pytest.raises(OSError, match="disk full"):
            artifact_store.write_artifact(path, "replacement")

        assert path.read_text(encoding="utf-8") == "original"
        assert [p.name for p in tmp_path.iterdir()] == ["a.json"]

    def test_unwritten_placeholder_is_removed_when_the_block_exits(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        with artifact_store.release_if_unwritten(path):
            pass

        assert not path.exists()

    def test_written_artifact_is_kept_when_the_block_exits(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        with artifact_store.release_if_unwritten(path):
            artifact_store.write_artifact(path, "{}\n")

        assert path.read_text(encoding="utf-8") == "{}\n"
