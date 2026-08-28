"""Tests for hooks/lib/testimprove_phase_state.py — the shared /test-improve
phase-state resolution module extracted from scripts/test_improve_resume.py
(issue #2094 Slice 1, Step 1.1).

Covers the second Gherkin scenario in the plan's Slice 1:
"The shared module is importable independently of the CLI script" — calling
scan_phase_files/resolve_auto directly (no subprocess, no CLI) returns the
same tokens/resolution that scripts/test_improve_resume.py's own
build_result() reports for the same directory. The first scenario
("test_improve_resume.py behavior is unchanged after extraction") is covered
by plugins/dev-team/tests/scripts/test_test_improve_resume.py, which is
unmodified by this extraction and stays green.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from test_improve_resume import build_result  # type: ignore[import-not-found]
from testimprove_phase_state import (  # type: ignore[import-not-found]
    VALID_BINDING_MODES,
    parse_binding_mode,
    read_binding_mode,
    read_phase0_text,
    resolve_auto,
    resolve_with_phase3_correction,
    scan_phase_files,
)


def _make_phase_files(root: Path, *tokens: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for t in tokens:
        (root / f"phase-{t}.md").write_text("done\n", encoding="utf-8")
    return root


def test_scan_and_resolve_match_cli_build_result(tmp_path):
    """Fixture memory dir with phase-0.md and phase-2.md: calling
    scan_phase_files/resolve_auto directly must agree with what
    scripts/test_improve_resume.py's build_result() reports for the same
    directory."""
    memory_dir = _make_phase_files(tmp_path / "my-repo", "0", "2")

    tokens = scan_phase_files(memory_dir)
    resolved_phase, highest, complete = resolve_auto(tokens)

    cli_exit_code, cli_payload = build_result(memory_dir, explicit=None)

    assert tokens == ["0", "2"]
    assert complete is False
    assert resolved_phase == "1"
    assert highest == "2"

    assert cli_exit_code == 0
    assert cli_payload["resolved_phase"] == resolved_phase
    assert cli_payload["latest_completed"] == f"phase-{highest}.md"
    assert cli_payload["complete"] == complete


def test_resolve_auto_empty_tokens_raises_value_error():
    """Documents resolve_auto's existing precondition (not a behavior
    change): an empty token list raises ValueError via the underlying
    max(). Callers — including a future direct consumer like the Slice 2
    guard hook — must guard against calling this before phase-0.md is
    confirmed to exist."""
    with pytest.raises(ValueError):
        resolve_auto([])


# ---------------------------------------------------------------------------
# Phase-3 correction (issue #2094 Slice 2 review fix #1): hoisted here from
# the guard hook so scripts/test_improve_resume.py and
# hooks/testimprove_phase_scope_guard.py agree on when Phase 3 is active.
# ---------------------------------------------------------------------------


def test_parse_binding_mode_rejects_invalid_value():
    """Fix #4: a value outside VALID_BINDING_MODES (a truncated/garbled
    write, e.g. `binding_mode: x`) is treated as absent, never as an
    implicit non-none mode."""
    assert parse_binding_mode("binding_mode: not-a-real-mode\n") is None


def test_parse_binding_mode_accepts_each_valid_value():
    for value in sorted(VALID_BINDING_MODES):
        assert parse_binding_mode(f"binding_mode: {value}\n") == value


def test_read_binding_mode_missing_file_returns_none(tmp_path):
    assert read_binding_mode(tmp_path / "nope") is None


def test_read_phase0_text_invalid_utf8_fails_open_not_raises(tmp_path):
    """Review fix (issue #2094 follow-up): `read_text(encoding="utf-8")`
    raises `UnicodeDecodeError` (a `ValueError`, not an `OSError`) on
    invalid UTF-8 — this must be caught and treated as "unreadable" (`None`)
    like a missing file, not propagate uncaught through an unguarded caller
    such as `scripts/test_improve_resume.py`'s `build_result()`."""
    memory_dir = tmp_path / "my-repo"
    memory_dir.mkdir()
    (memory_dir / "phase-0.md").write_bytes(b"binding_mode: none\n\xff\xfe")

    assert read_phase0_text(memory_dir) is None
    assert read_binding_mode(memory_dir) is None


def test_resolve_with_phase3_correction_returns_3_when_bdd_mode_and_no_gherkin(
    tmp_path,
):
    memory_dir = _make_phase_files(tmp_path / "my-repo", "0", "2")
    (memory_dir / "phase-0.md").write_text(
        "binding_mode: bdd-runner\n", encoding="utf-8"
    )

    resolved, highest, complete = resolve_with_phase3_correction(memory_dir)

    assert (resolved, highest, complete) == ("3", "2", False)


def test_resolve_with_phase3_correction_skipped_when_binding_mode_none(tmp_path):
    memory_dir = _make_phase_files(tmp_path / "my-repo", "0", "2")
    (memory_dir / "phase-0.md").write_text("binding_mode: none\n", encoding="utf-8")

    resolved, highest, complete = resolve_with_phase3_correction(memory_dir)

    assert (resolved, highest, complete) == ("1", "2", False)


def test_resolve_with_phase3_correction_skipped_when_gherkin_already_done(tmp_path):
    memory_dir = _make_phase_files(tmp_path / "my-repo", "0", "2")
    (memory_dir / "phase-0.md").write_text(
        "binding_mode: bdd-runner\n", encoding="utf-8"
    )
    (memory_dir / "gherkin.md").write_text("done\n", encoding="utf-8")

    resolved, highest, complete = resolve_with_phase3_correction(memory_dir)

    assert (resolved, highest, complete) == ("1", "2", False)


def test_resolve_with_phase3_correction_falls_back_on_malformed_phase0(tmp_path):
    """Judgment call (fix #1): scripts/test_improve_resume.py's own
    graceful-degradation contract — a malformed phase-0.md must not block a
    resume suggestion, so this function silently falls through to ordinary
    resolve_auto() resolution. This deliberately differs from
    hooks/testimprove_phase_scope_guard.py's `_resolve_active_phase`, which
    treats this same state as fail-open-with-audit (`status ==
    "none_in_flight"`, `reason == "malformed or missing phase-0.md"`) —
    resume's job is a best-effort suggestion, the guard's job is a
    confident block-or-allow decision, so the two consumers intentionally
    diverge only on this malformed-input edge case, not on the well-defined
    Phase-3 window itself (see test_guard_and_resume_agree_in_the_phase3_window
    in test_test_improve_phase_scope_guard.py)."""
    memory_dir = _make_phase_files(tmp_path / "my-repo", "0", "2")
    (memory_dir / "phase-0.md").write_text(
        "not a key-value line\n", encoding="utf-8"
    )

    resolved, highest, complete = resolve_with_phase3_correction(memory_dir)

    assert (resolved, highest, complete) == ("1", "2", False)


def test_module_importable_without_cli_module_in_fresh_interpreter():
    """The shared module loads standalone in a fresh interpreter that has
    only hooks/lib on sys.path — importing it must not pull in the CLI
    script (test_improve_resume) as a side effect. A bare
    `"scan_phase_files" in dir(sys.modules[...])` check in this same test
    process would be vacuous: this test file's own top-level
    `from test_improve_resume import build_result` above already puts the
    CLI module in sys.modules before this test runs, so only a fresh
    subprocess can prove real import-independence."""
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(_HOOKS_LIB_DIR)!r})\n"
        "import testimprove_phase_state\n"
        "assert 'test_improve_resume' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
