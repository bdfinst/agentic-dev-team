"""Tests for `mcp_tool_grants.run_grants_check` — the shared single-pass runner
extracted from the three near-duplicate MCP tool-grant check scripts (#1393),
which also closes the double read+parse regression on `--fix` (#1392).
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

from mcp_tool_grants import run_grants_check

REQUIRED = ["mcp__a__x", "mcp__b__y"]


def _agent(directory: Path, name: str, tools_line: str) -> Path:
    path = directory / f"{name}.md"
    path.write_text(f"---\nname: {name}\ntools: {tools_line}\n---\n# {name}\n", encoding="utf-8")
    return path


def test_detect_only_reports_missing_without_writing(tmp_path):
    path = _agent(tmp_path, "foo", "Read, Grep, Glob")
    before = path.read_text(encoding="utf-8")

    offenders, fixed, unfixable = run_grants_check({"foo": (path, REQUIRED)})

    assert offenders == {"foo": REQUIRED}
    assert fixed == {}
    assert unfixable == []
    assert path.read_text(encoding="utf-8") == before  # untouched


def test_apply_fix_writes_once_and_offenders_reflect_post_fix_state(tmp_path):
    path = _agent(tmp_path, "foo", "Read, Grep, Glob")

    offenders, fixed, unfixable = run_grants_check({"foo": (path, REQUIRED)}, apply_fix=True)

    assert fixed == {"foo": REQUIRED}
    assert offenders == {}  # computed from the already-fixed text, not stale
    assert unfixable == []
    assert "mcp__a__x" in path.read_text(encoding="utf-8")


def test_apply_fix_reads_target_file_exactly_once(tmp_path, monkeypatch):
    # Regression guard for #1392: the previous per-script pattern
    # (`apply_fixes()` then a separate `find_offenders()` call) read every
    # target file's text from disk twice on `--fix`. The shared runner must
    # do a single `read_text()` per target regardless of `apply_fix`.
    path = _agent(tmp_path, "foo", "Read, Grep, Glob")
    read_calls = []
    real_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        if self == path:
            read_calls.append(1)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    run_grants_check({"foo": (path, REQUIRED)}, apply_fix=True)

    assert len(read_calls) == 1


def test_missing_file_is_an_offender_and_not_unfixable(tmp_path):
    missing = tmp_path / "ghost.md"

    offenders, fixed, unfixable = run_grants_check({"ghost": (missing, REQUIRED)}, apply_fix=True)

    assert offenders == {"ghost": REQUIRED}
    assert fixed == {}
    assert unfixable == []  # no file to attempt fixing — distinct from unfixable


def test_no_tools_line_is_unfixable_and_reported_as_fully_missing(tmp_path):
    path = tmp_path / "notools.md"
    path.write_text("---\nname: notools\n---\n# body\n", encoding="utf-8")

    offenders, fixed, unfixable = run_grants_check({"notools": (path, REQUIRED)}, apply_fix=True)

    assert unfixable == ["notools"]
    assert fixed == {}
    assert offenders == {"notools": REQUIRED}


def test_already_compliant_target_is_not_an_offender_and_nothing_is_fixed(tmp_path):
    path = _agent(tmp_path, "foo", "Read, Grep, Glob, " + ", ".join(REQUIRED))

    offenders, fixed, unfixable = run_grants_check({"foo": (path, REQUIRED)}, apply_fix=True)

    assert offenders == {}
    assert fixed == {}
    assert unfixable == []


def test_second_apply_fix_pass_is_idempotent(tmp_path):
    path = _agent(tmp_path, "foo", "Read, Grep, Glob")
    run_grants_check({"foo": (path, REQUIRED)}, apply_fix=True)

    offenders, fixed, unfixable = run_grants_check({"foo": (path, REQUIRED)}, apply_fix=True)

    assert offenders == {}
    assert fixed == {}
    assert unfixable == []
