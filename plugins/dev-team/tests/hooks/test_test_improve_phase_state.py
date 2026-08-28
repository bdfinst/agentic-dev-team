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
    resolve_auto,
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
