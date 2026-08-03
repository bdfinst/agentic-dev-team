"""Unit tests for skills/code-review/scripts/changed_file_list.py (#1734).

Covers parsing `git diff --name-status` output into the changed-file list
that both the `project-structure` context payload (arch-review/doc-review/
domain-review) and `select_lenses.py`'s added-only `Scope:` gate (#1733)
consume from a single source.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import changed_file_list

_SCRIPT = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "code-review"
    / "scripts"
    / "changed_file_list.py"
)


class TestParseNameStatus:
    def test_added_modified_deleted(self):
        files = changed_file_list.parse_name_status(
            ["A\tfoo.py", "M\tbar.py", "D\tbaz.py"]
        )
        assert files == [
            {"path": "foo.py", "status": "A"},
            {"path": "bar.py", "status": "M"},
            {"path": "baz.py", "status": "D"},
        ]

    def test_rename_keeps_new_path_and_letter_only(self):
        files = changed_file_list.parse_name_status(["R100\told.py\tnew.py"])
        assert files == [{"path": "new.py", "status": "R"}]

    def test_copy_keeps_new_path_and_letter_only(self):
        files = changed_file_list.parse_name_status(["C75\tsrc.py\tcopy.py"])
        assert files == [{"path": "copy.py", "status": "C"}]

    def test_blank_lines_ignored(self):
        assert changed_file_list.parse_name_status(["", "  ", "A\tfoo.py"]) == [
            {"path": "foo.py", "status": "A"}
        ]

    def test_malformed_line_skipped_not_raised(self):
        assert changed_file_list.parse_name_status(["not-a-name-status-line"]) == []

    def test_empty_status_field_skipped(self):
        # A tab with nothing before it: len(parts) == 2, but status_field == "".
        assert changed_file_list.parse_name_status(["\tfoo.py"]) == []

    def test_empty_path_skipped(self):
        assert changed_file_list.parse_name_status(["A\t"]) == []
        assert changed_file_list.parse_name_status(["A\t   "]) == []

    def test_empty_input(self):
        assert changed_file_list.parse_name_status([]) == []

    def test_rename_and_copy_are_not_added_by_design(self):
        # Pins the deliberate choice recorded in the module docstring: a
        # rename/copy's new path is excluded from "added" even though it did
        # not exist under that name before.
        files = changed_file_list.parse_name_status(
            ["R100\told.py\tnew.py", "C75\tsrc.py\tcopy.py"]
        )
        assert [f["status"] for f in files] == ["R", "C"]

    def test_duplicate_path_with_conflicting_status_keeps_both_entries(self):
        # A file staged as new (A) then further edited in the worktree (M)
        # yields two lines for the same path when a caller unions two diffs
        # (SKILL.md step 3's auto-scope). This module does not dedupe —
        # pinning that both survive in `files`, and the A status makes the
        # path count as "added" regardless of ordering.
        files = changed_file_list.parse_name_status(["A\tsrc/App.tsx", "M\tsrc/App.tsx"])
        assert files == [
            {"path": "src/App.tsx", "status": "A"},
            {"path": "src/App.tsx", "status": "M"},
        ]


class TestEvaluate:
    def test_added_list_is_status_a_only(self):
        result = changed_file_list.evaluate(
            ["A\tnew.py", "M\texisting.py", "A\tsrc/other.tsx"]
        )
        assert result["added"] == ["new.py", "src/other.tsx"]
        assert len(result["files"]) == 3

    def test_no_added_files_yields_empty_added_list(self):
        result = changed_file_list.evaluate(["M\tfoo.py", "D\tbar.py"])
        assert result["added"] == []

    def test_empty_input_yields_empty_result(self):
        assert changed_file_list.evaluate([]) == {"files": [], "added": []}

    def test_renamed_or_copied_path_absent_from_added(self):
        result = changed_file_list.evaluate(["R100\told.tsx\tnew.tsx", "C75\ta.tsx\tb.tsx"])
        assert result["added"] == []

    def test_duplicate_path_conflicting_status_still_counts_as_added(self):
        result = changed_file_list.evaluate(["M\tsrc/App.tsx", "A\tsrc/App.tsx"])
        assert result["added"] == ["src/App.tsx"]


def _run(*name_status_lines):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--name-status", *name_status_lines],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_cli_reports_added_files(self):
        r = _run("A\tnew.py", "M\texisting.py")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["added"] == ["new.py"]
        assert {"path": "existing.py", "status": "M"} in out["files"]

    def test_cli_stdin_mode(self):
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--name-status-from", "-"],
            input="A\tnew.py\nM\texisting.py\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0
        assert json.loads(r.stdout)["added"] == ["new.py"]

    def test_cli_no_args_yields_empty_result(self):
        r = _run()
        assert r.returncode == 0
        assert json.loads(r.stdout) == {"files": [], "added": []}

    def test_cli_name_status_from_real_file(self, tmp_path):
        name_status_file = tmp_path / "name-status.txt"
        name_status_file.write_text("A\tnew.py\nM\texisting.py\n")
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--name-status-from", str(name_status_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0
        assert json.loads(r.stdout)["added"] == ["new.py"]

    def test_cli_name_status_from_missing_file_fails_open(self, tmp_path):
        # A missing/unreadable --name-status-from path must not crash the
        # whole invocation — it contributes no lines, same as any other
        # unparseable input this module already tolerates.
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--name-status-from", str(tmp_path / "nope.txt")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0
        assert json.loads(r.stdout) == {"files": [], "added": []}
