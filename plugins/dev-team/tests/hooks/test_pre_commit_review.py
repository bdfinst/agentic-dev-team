"""Unit tests for hooks/pre_commit_review.py (#1886).

This module is now a documented no-op (see its own module docstring): the
review-corroboration gate moved to `hooks/pre_pr_review.py`, triggered by
`gh pr create` rather than `git commit`. Every prior test here pinning the
git-commit-gating behavior (hash match, dispatch corroboration, exemptions,
the `--no-verify`/`GATE_BYPASS_REASON` bypass, multi-target `-C` resolution,
`-a`/pathspec-form-commit detection, cosmetic-delta carry-forward) has had
its INTENT ported to `test_pre_pr_review.py`'s own suite, adapted to the new
trigger point — see that file's own module docstring for the mapping.

These tests pin only the no-op contract: ANY input, including a `git commit`
that would have been blocked under the old gate, now allows unconditionally.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def _run(payload: dict | str, cwd: Path) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=stdin,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_commit_that_would_have_been_blocked_under_the_old_gate_now_allows(
    tmp_path: Path,
) -> None:
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    # No .review-passed, no dispatch evidence — the old gate would have
    # blocked this with exit 2. It now allows unconditionally.
    result = _run({"tool_input": {"command": "git commit -m x"}, "cwd": str(tmp_path)}, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_a_no_verify_commit_with_no_bypass_reason_now_allows(tmp_path: Path) -> None:
    # The old gate blocked a --no-verify commit without GATE_BYPASS_REASON.
    # There is no gate left to bypass, so this now allows too.
    result = _run(
        {"tool_input": {"command": "git commit --no-verify -m x"}, "cwd": str(tmp_path)},
        tmp_path,
    )
    assert result.returncode == 0


def test_a_non_commit_command_allows(tmp_path: Path) -> None:
    result = _run({"tool_input": {"command": "echo hi"}, "cwd": str(tmp_path)}, tmp_path)
    assert result.returncode == 0


def test_malformed_stdin_allows(tmp_path: Path) -> None:
    result = _run("not json{{{", tmp_path)
    assert result.returncode == 0


def test_empty_stdin_allows(tmp_path: Path) -> None:
    result = _run("", tmp_path)
    assert result.returncode == 0


def test_no_side_effects_written(tmp_path: Path) -> None:
    """No gate file, no bypass audit, no boundary event — this hook no
    longer touches `.claude/` at all."""
    _run({"tool_input": {"command": "git commit --no-verify -m x"}, "cwd": str(tmp_path)}, tmp_path)
    assert not (tmp_path / ".claude").exists()
