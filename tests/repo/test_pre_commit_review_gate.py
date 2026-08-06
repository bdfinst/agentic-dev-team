"""#193 - the review gate binds diff CONTENT (via review-gate-hash.sh /
branch_diff_gate_hash), so editing a reviewed file re-blocks the gate.

#1886: the review-corroboration gate moved from `git commit` to
`gh pr create`. `pre_commit_review.py` (this file's original subject) is now
a documented no-op — every scenario this file used to pin against it now
belongs to `pre_pr_review.py`, ported below at the new trigger point. See
`plugins/dev-team/tests/hooks/test_pre_pr_review.py` for the fuller unit
coverage; these repo-level tests keep the historical #193/#673 pointer alive
at the new mechanism.

Originally ported from tests/repo/review_gate_hash_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

COMMIT_HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"
PR_HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"
GATEHASH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "review_gate_hash.py"


@pytest.fixture
def work(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(tmp_path), env=hermetic_env, check=True)
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
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=str(tmp_path), env=hermetic_env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature"], cwd=str(tmp_path), env=hermetic_env, check=True
    )
    return tmp_path


def _git(
    work: Path, hermetic_env: dict[str, str], *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(work),
        env=hermetic_env,
        check=False,
        capture_output=True,
        text=True,
    )


def _pr_create_hook(
    work: Path, hermetic_env: dict[str, str]
) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": "gh pr create"}, "cwd": str(work)})
    return subprocess.run(
        [sys.executable, str(PR_HOOK)],
        cwd=str(work),
        env=hermetic_env,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )


def test_commit_hook_is_now_a_no_op(work: Path, hermetic_env: dict[str, str]) -> None:
    """#1886: the commit-time gate is gone — a bare `git commit` allows
    unconditionally, with no gate file and no dispatch evidence needed."""
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}, "cwd": str(work)})
    result = subprocess.run(
        [sys.executable, str(COMMIT_HOOK)],
        cwd=str(work),
        env=hermetic_env,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def _branch_diff_hash(work: Path, hermetic_env: dict[str, str]) -> str:
    result = subprocess.run(
        [sys.executable, str(GATEHASH)],
        cwd=str(work),
        env=hermetic_env,
        capture_output=True,
        text=True,
        check=False,
    )
    # review_gate_hash.py's CLI prints review_gate_hash() (staged patch), not
    # the branch-diff hash — compute the latter directly via the library.
    del result
    sys.path.insert(0, str(GATEHASH.parent))
    import review_gate_hash as _rgh  # type: ignore[import-not-found]

    return _rgh.branch_diff_gate_hash("main", cwd=work)


def _write_gate(work: Path, hermetic_env: dict[str, str]) -> None:
    h = _branch_diff_hash(work, hermetic_env)
    gate_path = work / ".claude" / "memory" / ".pr-review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(h)


def _write_dispatch_evidence(work: Path, hermetic_env: dict[str, str]) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with 2 distinct genuine
    review-agent dispatches (#1461/#1886), bound to the CURRENT branch-diff
    hash."""
    subject_hash = _branch_diff_hash(work, hermetic_env)
    log = work / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Anchored slightly in the past — the PR-time gate anchors its recency
    # window on `now()` (see pre_pr_review.py's own docstring), not a gate
    # file's mtime, so this just needs to land inside the window.
    stamp = (datetime.now(UTC) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a", encoding="utf-8") as fh:
        for agent in ("security-review", "structure-review"):
            fh.write(
                json.dumps(
                    {
                        "ts": stamp,
                        "hook": "agent_dispatch_ledger",
                        "tool": "Agent",
                        "decision": "record",
                        "matched_rule": agent,
                        "plugin_version": "0.0.0",
                        "subject_hash": subject_hash,
                    }
                )
                + "\n"
            )


def test_gate_exact_branch_diff_that_was_reviewed_allows_pr_create(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _git(work, hermetic_env, "commit", "-q", "-m", "feature work")
    _write_dispatch_evidence(work, hermetic_env)
    _write_gate(work, hermetic_env)
    result = _pr_create_hook(work, hermetic_env)
    assert result.returncode == 0
    assert not (
        work / ".claude" / "memory" / ".pr-review-passed"
    ).is_file()  # consumed on success


def test_gate_editing_a_reviewed_files_content_reblocks_pr_create(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _git(work, hermetic_env, "commit", "-q", "-m", "feature work")
    _write_gate(work, hermetic_env)  # reviewed the branch diff @ v1
    (work / "a.ts").write_text("v2-unreviewed\n")
    _git(work, hermetic_env, "add", "a.ts")
    _git(work, hermetic_env, "commit", "-q", "-m", "unreviewed follow-up")
    result = _pr_create_hook(work, hermetic_env)
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout + result.stderr


def test_gate_writer_and_hook_compute_the_same_branch_diff_hash(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("line1\nline2\n")
    _git(work, hermetic_env, "add", "a.ts")
    _git(work, hermetic_env, "commit", "-q", "-m", "feature work")
    _write_dispatch_evidence(work, hermetic_env)
    _write_gate(work, hermetic_env)
    result = _pr_create_hook(work, hermetic_env)
    assert result.returncode == 0
