"""The harness's diff of a trial's working copy: every change the agent made is visible."""

from __future__ import annotations

import hashlib
from pathlib import Path

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from model_effort import work_diff


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    pristine, work = tmp_path / "pristine", tmp_path / "work"
    pristine.mkdir()
    work.mkdir()
    return pristine, work


class TestPresence:
    def test_a_deleted_empty_file_is_shown(self, trees):
        pristine, work = trees
        (pristine / "empty.txt").write_text("")

        diff = work_diff.working_copy_diff(pristine, work)

        assert diff != work_diff.NO_CHANGES_TEXT
        assert "empty.txt" in diff and "absent" in diff

    def test_a_new_empty_file_is_shown(self, trees):
        pristine, work = trees
        (work / "marker").write_text("")

        diff = work_diff.working_copy_diff(pristine, work)

        assert diff != work_diff.NO_CHANGES_TEXT
        assert "marker" in diff and "absent" in diff


class TestBinaryContent:
    @pytest.mark.parametrize(
        ("before", "after"),
        [(b"\x00\x01", b"\x00\x02"), (b"\xff\xfe", b"\xfe\xff")],
        ids=["binary", "not-utf8"],
    )
    def test_a_same_size_change_is_shown_with_both_digests(self, trees, before, after):
        pristine, work = trees
        (pristine / "blob.bin").write_bytes(before)
        (work / "blob.bin").write_bytes(after)

        diff = work_diff.working_copy_diff(pristine, work)

        assert diff != work_diff.NO_CHANGES_TEXT
        assert hashlib.sha256(before).hexdigest() in diff
        assert hashlib.sha256(after).hexdigest() in diff


class TestGitDirectories:
    def test_a_nested_git_directory_is_part_of_the_agents_work(self, trees):
        pristine, work = trees
        (work / "vendor" / ".git").mkdir(parents=True)
        (work / "vendor" / ".git" / "hooks.sh").write_text("echo planted\n")

        diff = work_diff.working_copy_diff(pristine, work)

        assert "vendor/.git/hooks.sh" in diff

    def test_the_top_level_git_directory_stays_skipped(self, trees):
        pristine, work = trees
        (work / ".git").mkdir()
        (work / ".git" / "HEAD").write_text("ref")

        assert work_diff.working_copy_diff(pristine, work) == work_diff.NO_CHANGES_TEXT
