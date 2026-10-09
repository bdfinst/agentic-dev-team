"""Replacing staged and snapshot directories in recorded text (model_effort.path_scrub)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from model_effort import path_scrub, runner, snapshot


class TestScrubPaths:
    def test_snapshot_directory_becomes_a_placeholder_even_inside_the_temp_directory(
        self, tmp_path
    ):
        root = Path(tempfile.mkdtemp(prefix=snapshot.SNAPSHOT_DIR_PREFIX))
        try:
            scrubbed = path_scrub.scrub_paths(
                f"cannot read {root}/plugin/knowledge/x.md", None, root
            )
        finally:
            root.rmdir()

        assert scrubbed == "cannot read <snapshot>/plugin/knowledge/x.md"

    def test_home_directory_becomes_a_tilde(self, tmp_path, monkeypatch):
        home = tmp_path / "alice"
        monkeypatch.setenv("HOME", str(home))

        scrubbed = path_scrub.scrub_paths(f"cannot open {home}/bin/claude", None)

        assert scrubbed == "cannot open ~/bin/claude"

    def test_temp_directory_becomes_a_placeholder(self, monkeypatch):
        monkeypatch.setenv("HOME", "/nowhere/home")
        temp = tempfile.gettempdir()

        scrubbed = path_scrub.scrub_paths(f"cannot write {temp}/x.json", None)

        assert scrubbed == "cannot write <tmp>/x.json"

    def test_staged_directory_becomes_a_placeholder_even_inside_the_temp_directory(
        self,
    ):
        staged = Path(tempfile.mkdtemp(prefix=runner.TEMP_DIR_PREFIX))
        try:
            scrubbed = path_scrub.scrub_paths(f"cannot read {staged}/form.html", staged)
        finally:
            staged.rmdir()

        assert scrubbed == "cannot read <staged>/form.html"

    def test_the_resolved_spelling_of_a_directory_is_scrubbed_too(self, tmp_path):
        link = tmp_path / "link"
        target = tmp_path / "target"
        target.mkdir()
        link.symlink_to(target)

        scrubbed = path_scrub.scrub_paths(f"in {target.resolve()}/x", link)

        assert scrubbed == "in <staged>/x"

    def test_home_inside_the_temp_directory_is_scrubbed_as_home(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "alice"
        monkeypatch.setenv("HOME", str(home))

        scrubbed = path_scrub.scrub_paths(f"{home}/bin and {tmp_path}/other", None)

        assert scrubbed.startswith("~/bin and <tmp>")

    def test_a_root_home_directory_leaves_the_text_alone(self, monkeypatch):
        monkeypatch.setenv("HOME", "/")

        assert path_scrub.scrub_paths("/usr/bin/claude", None) == "/usr/bin/claude"
