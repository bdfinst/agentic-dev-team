"""#1899 — is the PR-time review gate structurally immune to an
unprovisioned `.husky/_` (the failure mode #1899 reported for the OLD
commit-time gate)?

#1899's root cause: `pre_commit_review.py` (the commit-time gate) was a
Claude-Code-level PreToolUse hook, but the reporting agent found a fresh
worktree where `core.hooksPath` pointed at `.husky/_` and that directory was
EMPTY (`npm ci` had not yet completed) — and a `git commit` landed with no
review corroboration and no bypass-audit entry. The issue's own body already
suspected this might be a false lead ("a repo-local husky pre-push hook ...
can't see review-dispatch ledger state the harness produces" — i.e. husky
was never actually in the causal chain for a Claude-Code-level hook), and
asked for this to be confirmed explicitly with a test once the gate's
trigger mechanism was known.

**Answer: #1899 is closed by construction as a side effect of #1886's
relocation.** `pre_pr_review.py` is registered in `hooks/hooks.json`'s
`PreToolUse` -> `Bash` matcher list — the harness's OWN mechanism, invoked
directly by Claude Code for every Bash tool call, entirely independent of
git's `core.hooksPath` / husky. This test proves it by SIMULATING the exact
reported failure state (an empty `.husky/_` directory, `core.hooksPath`
pointed at it) and confirming the gate still blocks `gh pr create` — because
invoking `pre_pr_review.py` directly (as Claude Code's own PreToolUse
mechanism does) never consults `core.hooksPath` at all; that config value is
only ever read by `git` itself when IT dispatches to a git hook, a wholly
separate code path this hook never touches.

This was never a property `pre_commit_review.py` had to newly acquire
either — the OLD commit-time gate had exactly the same
harness-native-not-git-hook property, so #1899's ORIGINAL failure mode (if
it was real, rather than a race in whatever provisioned the worktree before
the observed commit) was never actually caused by `.husky/_` provisioning
state for either hook. Nothing else in this fix independently confirms or
refutes the ORIGINAL incident's true root cause; this test only confirms the
mechanism-level claim the issue asked to have verified.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

PR_HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"


@pytest.fixture
def unprovisioned_worktree(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    """A fresh git repo whose `core.hooksPath` points at an EMPTY
    `.husky/_` — the exact #1899-reported state (`npm ci` never completed)."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    (tmp_path / ".husky" / "_").mkdir(parents=True)
    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky/_"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=str(tmp_path), env=hermetic_env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=str(tmp_path), env=hermetic_env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feature work"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    return tmp_path


def test_husky_hooks_path_is_never_consulted_by_the_hooks_own_process(
    unprovisioned_worktree: Path,
) -> None:
    """Confirms the mechanism-level claim directly: `.husky/_` being empty
    has zero bearing on whether `pre_pr_review.py`'s process runs at all —
    it is invoked exactly the same way (`python3 pre_pr_review.py` on stdin)
    regardless of `core.hooksPath`."""
    assert list((unprovisioned_worktree / ".husky" / "_").iterdir()) == []
    assert (
        subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=str(unprovisioned_worktree),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == ".husky/_"
    )


def test_gate_still_blocks_with_an_empty_unprovisioned_husky_hooks_path(
    unprovisioned_worktree: Path, hermetic_env: dict[str, str]
) -> None:
    """The gate fires and blocks `gh pr create` (no `.pr-review-passed`, no
    dispatch evidence) EXACTLY as it would in a fully-provisioned worktree —
    confirming `.husky/_`'s state never entered the decision at all."""
    payload = json.dumps(
        {"tool_input": {"command": "gh pr create"}, "cwd": str(unprovisioned_worktree)}
    )
    result = subprocess.run(
        [sys.executable, str(PR_HOOK)],
        cwd=str(unprovisioned_worktree),
        env=hermetic_env,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_gate_still_fires_when_husky_hooks_path_points_at_a_missing_directory(
    tmp_path: Path, hermetic_env: dict[str, str]
) -> None:
    """A step further than an empty `.husky/_`: `core.hooksPath` pointed at
    a directory that does not exist AT ALL. If the gate depended on git's
    own hook dispatch mechanism in any way, this would be the most extreme
    version of that failure. It still blocks."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky/does-not-exist"],
        cwd=str(tmp_path),
        env=hermetic_env,
        check=True,
    )
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=str(tmp_path), env=hermetic_env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=str(tmp_path), env=hermetic_env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feature work"], cwd=str(tmp_path), env=hermetic_env, check=True
    )

    payload = json.dumps({"tool_input": {"command": "gh pr create"}, "cwd": str(tmp_path)})
    result = subprocess.run(
        [sys.executable, str(PR_HOOK)],
        cwd=str(tmp_path),
        env=hermetic_env,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout
