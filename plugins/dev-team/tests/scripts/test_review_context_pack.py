"""Unit tests for skills/code-review/scripts/review_context_pack.py (#2006).

The pack exists to cut a measured 4.31x re-read multiplier across review
panels. What these tests defend is not the saving — it is that the saving
never costs coverage. A pack that quietly drops a file hands every lens in the
panel a change that looks fully reviewed and is not, and the panel's silence
then reads as "no findings here." So every omission path is pinned to be both
*visible in the pack body* and *reported in the manifest*, and the honesty of
the rendered header is pinned too.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import review_context_pack as rcp


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    return tmp_path


class TestLineNumbering:
    def test_bodies_are_numbered_so_findings_can_cite_line_numbers(self):
        assert rcp.number_lines("x\ny\n") == "1\tx\n2\ty"

    def test_numbering_pads_to_a_consistent_width(self):
        """Ragged columns make a body harder to scan, and a lens counting lines
        by eye is exactly what the pack removes the need for."""
        out = rcp.number_lines("\n".join(str(i) for i in range(1, 11)))
        assert out.startswith(" 1\t1")
        assert "10\t10" in out

    def test_empty_file_does_not_raise(self):
        assert rcp.number_lines("") == ""


class TestUnreadableBodiesAreNamedNotDropped:
    def test_missing_file_reports_a_reason(self, repo):
        text, reason = rcp.read_file_text(repo / "src" / "gone.py")
        assert text is None
        assert "deleted" in reason

    def test_binary_file_is_detected(self, repo):
        (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
        text, reason = rcp.read_file_text(repo / "blob.bin")
        assert text is None and reason == "binary"

    def test_invalid_utf8_is_detected_without_raising(self, repo):
        (repo / "bad.txt").write_bytes(b"\xff\xfe latin \xe9")
        text, reason = rcp.read_file_text(repo / "bad.txt")
        assert text is None and "UTF-8" in reason

    def test_directory_is_not_treated_as_a_body(self, repo):
        text, reason = rcp.read_file_text(repo / "src")
        assert text is None and reason == "directory"


class TestBudgetNeverTruncatesAFileSilently:
    def test_an_oversized_file_is_omitted_whole_and_named(self, repo):
        (repo / "huge.py").write_text("x = 1\n" * 5000, encoding="utf-8")
        included, omitted = rcp.select_bodies(
            ["huge.py", "src/a.py"], repo, max_bytes=10_000, max_file_bytes=1_000
        )
        assert [e["file"] for e in included] == ["src/a.py"]
        assert omitted[0]["file"] == "huge.py"
        assert "per-file cap" in omitted[0]["reason"]

    def test_one_huge_file_does_not_hide_the_smaller_ones_behind_it(self, repo):
        """Selection must keep walking past something that does not fit.
        Stopping at the first oversized file would drop every later file for a
        reason that has nothing to do with them — and the panel would never
        know which behavior it got, since both report 'omitted'."""
        (repo / "huge.py").write_text("x = 1\n" * 5000, encoding="utf-8")
        included, _ = rcp.select_bodies(
            ["huge.py", "src/a.py", "src/b.py"], repo, max_bytes=10_000, max_file_bytes=1_000
        )
        assert [e["file"] for e in included] == ["src/a.py", "src/b.py"]

    def test_budget_exhaustion_is_reported_distinctly_from_the_per_file_cap(self, repo):
        included, omitted = rcp.select_bodies(
            ["src/a.py", "src/b.py"], repo, max_bytes=25, max_file_bytes=10_000
        )
        assert len(included) == 1
        assert omitted[0]["reason"] == "pack byte budget exhausted"

    def test_included_bodies_are_never_partial(self, repo):
        """The whole point: a body in the pack is the complete file. A lens
        citing line 40 of a body that stops at line 30 reports a phantom."""
        included, _ = rcp.select_bodies(["src/a.py"], repo, 10_000, 10_000)
        assert included[0]["body"].endswith("return 1")


class TestRenderedPackIsHonest:
    def test_omitted_files_are_listed_in_the_body_not_only_the_manifest(self, repo):
        (repo / "huge.py").write_text("x = 1\n" * 5000, encoding="utf-8")
        manifest = rcp.build(
            files=["huge.py", "src/a.py"], cwd=repo, base_ref="HEAD",
            max_bytes=10_000, max_file_bytes=1_000, diff_text="",
        )
        body = (repo / ".claude" / "review-context").glob("pack-*.md")
        text = next(body).read_text(encoding="utf-8")
        assert "## NOT included in this pack" in text
        assert "huge.py" in text.split("## NOT included in this pack")[1]
        assert "Open them directly" in text
        assert manifest["complete"] is False

    def test_a_complete_pack_has_no_omission_section(self, repo):
        manifest = rcp.build(
            files=["src/a.py"], cwd=repo, base_ref="HEAD",
            max_bytes=10_000, max_file_bytes=10_000, diff_text="",
        )
        text = Path(manifest["path"]).read_text(encoding="utf-8")
        assert "## NOT included" not in text
        assert manifest["complete"] is True

    def test_paths_without_a_status_are_not_labelled_full_repository_scope(self, repo):
        """Regression: when the caller supplied paths but no change types, the
        header read '(no change list — full-repository scope)', telling a lens
        there was no diff when there was one. Absence of a *status* is not
        absence of a *change*."""
        manifest = rcp.build(
            files=["src/a.py"], cwd=repo, base_ref="HEAD",
            max_bytes=10_000, max_file_bytes=10_000, diff_text="",
        )
        text = Path(manifest["path"]).read_text(encoding="utf-8")
        section = text.split("## Changed files")[1].split("## Diff")[0]
        assert "full-repository scope" not in section
        assert "src/a.py" in section

    def test_statuses_are_rendered_when_supplied(self, repo):
        manifest = rcp.build(
            files=["src/a.py"], cwd=repo, base_ref="HEAD", changed=[("src/a.py", "A")],
            max_bytes=10_000, max_file_bytes=10_000, diff_text="",
        )
        text = Path(manifest["path"]).read_text(encoding="utf-8")
        assert "`A` src/a.py" in text

    def test_pack_tells_lenses_they_may_still_read_other_files(self, repo):
        """The pack narrows repeated reads, not the review. A lens that reads
        it as a closed world stops tracing callers into unchanged files."""
        manifest = rcp.build(
            files=["src/a.py"], cwd=repo, base_ref="HEAD",
            max_bytes=10_000, max_file_bytes=10_000, diff_text="",
        )
        text = Path(manifest["path"]).read_text(encoding="utf-8")
        assert "NOT listed here" in text


class TestNameStatusParsing:
    def test_plain_rows(self):
        assert rcp.parse_name_status(["M\tsrc/a.py", "A\tsrc/b.py"]) == [
            ("src/a.py", "M"), ("src/b.py", "A")
        ]

    def test_rename_keeps_the_new_path(self):
        """`R100\told\tnew` — the new path is what exists on disk and what a
        finding cites. Keeping the old one would make every body read fail."""
        assert rcp.parse_name_status(["R100\tsrc/old.py\tsrc/new.py"]) == [
            ("src/new.py", "R")
        ]

    def test_copy_keeps_the_new_path(self):
        assert rcp.parse_name_status(["C75\tsrc/a.py\tsrc/c.py"]) == [("src/c.py", "C")]

    def test_malformed_rows_are_skipped(self):
        assert rcp.parse_name_status(["", "junk", "\tno-status"]) == []


class TestDeterminism:
    def test_same_input_yields_the_same_pack_path(self, repo):
        a = rcp.build(files=["src/b.py", "src/a.py"], cwd=repo, base_ref="HEAD",
                      max_bytes=10_000, max_file_bytes=10_000, diff_text="")
        b = rcp.build(files=["src/a.py", "src/b.py"], cwd=repo, base_ref="HEAD",
                      max_bytes=10_000, max_file_bytes=10_000, diff_text="")
        assert a["path"] == b["path"], "input order must not change the pack"

    def test_duplicate_paths_are_collapsed(self, repo):
        m = rcp.build(files=["src/a.py", "src/a.py"], cwd=repo, base_ref="HEAD",
                      max_bytes=10_000, max_file_bytes=10_000, diff_text="")
        assert m["files_requested"] == 1


class TestCli:
    def _run(self, cwd, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "review_context_pack.py"),
             "--cwd", str(cwd), *args],
            capture_output=True, text=True, timeout=60, check=False, input=stdin,
        )

    def test_no_files_exits_nonzero_rather_than_writing_an_empty_pack(self, repo):
        result = self._run(repo, "--files-from", "-", stdin="")
        assert result.returncode == 1
        assert json.loads(result.stdout)["path"] is None

    def test_manifest_is_parseable_and_names_the_pack(self, repo):
        result = self._run(repo, "--files-from", "-", stdin="src/a.py\n")
        assert result.returncode == 0, result.stderr
        manifest = json.loads(result.stdout)
        assert manifest["files_included"] == ["src/a.py"]
        assert manifest["pack_bytes"] > 0
