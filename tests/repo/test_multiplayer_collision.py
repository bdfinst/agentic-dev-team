"""#109 Phase 1 — the multiplayer collision that REMAINS even after the gate
is content-bound (#193): two agents sharing ONE working tree share a single
gate file and clobber each other's evidence. The resolution is operational,
not a gate change — one git worktree per agent (see
plugins/dev-team/docs/concurrent-use.md).

#1886: the review-corroboration gate moved from `git commit` to
`gh pr create`, so this collision now applies to `.claude/memory/
.pr-review-passed` at PR-creation time, not `.review-passed` at every
commit. `pre_commit_review.py` (this file's original subject) is now a
documented no-op — `git commit` always allows unconditionally, so the
collision scenario no longer applies there at all. The scenario is ported
below to `pre_pr_review.py`.

Content-binding behavior itself is covered by test_review_gate_hash.py
(plugins/dev-team/tests/hooks/). Originally ported from
tests/repo/multiplayer_collision_tests.bats (issue #671).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

COMMIT_HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"
PR_HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_pr_review.py"
LIB_DIR = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
import review_gate_hash as _rgh  # type: ignore[import-not-found]


def _git_env() -> dict:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }


@pytest.fixture
def work(tmp_path: Path) -> Path:
    env = _git_env()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=tmp_path, env=env, check=True
    )
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def _commit_hook(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMMIT_HOOK)],
        input='{"tool_input":{"command":"git commit -m x"}}',
        cwd=cwd,
        env=_git_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def _pr_create_hook(cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": "gh pr create"}, "cwd": str(cwd)})
    return subprocess.run(
        [sys.executable, str(PR_HOOK)],
        input=payload,
        cwd=cwd,
        env=_git_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def test_commit_hook_no_longer_gates_so_there_is_no_commit_time_collision(
    work: Path,
) -> None:
    """#1886: `git commit` allows unconditionally now — there is no gate
    file left to collide over at commit time."""
    (work / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=work, env=_git_env(), check=True)
    result = _commit_hook(work)
    assert result.returncode == 0


def _write_gate(cwd: Path) -> None:
    gate_path = cwd / ".claude" / "memory" / ".pr-review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(_rgh.branch_diff_gate_hash("main", cwd=cwd))


def _write_dispatch_evidence(cwd: Path) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with 2 distinct genuine
    review-agent dispatches (#1461/#1886), bound to the CURRENT branch-diff
    hash."""
    subject_hash = _rgh.branch_diff_gate_hash("main", cwd=cwd)
    log = cwd / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a", encoding="utf-8") as fh:
        for agent in ("security-review", "structure-review"):
            fh.write(
                json.dumps(
                    {
                        "ts": now,
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


def test_baseline_gate_written_for_current_branch_diff_allows_pr_create(
    work: Path,
) -> None:
    (work / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=work, env=_git_env(), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feature work"], cwd=work, env=_git_env(), check=True
    )
    _write_dispatch_evidence(work)
    _write_gate(work)
    res = _pr_create_hook(work)
    assert res.returncode == 0, res.stdout + res.stderr


def test_collision_a_second_agent_overwriting_pr_review_passed_falsely_blocks_the_first(
    work: Path,
) -> None:
    (work / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=work, env=_git_env(), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feature work"], cwd=work, env=_git_env(), check=True
    )
    _write_gate(work)  # agent A passed review for its branch diff
    gate_path = work / ".claude" / "memory" / ".pr-review-passed"
    gate_path.write_text("a-different-agents-hash\n")  # agent B (same tree) overwrote it
    res = _pr_create_hook(work)  # A opens its PR for its still-current branch
    assert res.returncode == 2  # ...and is blocked despite having passed
    assert "BLOCKED" in res.stdout
    # NOT fixed by content-hashing — two agents in one tree share one gate
    # file. Fix is operational: one worktree per agent (concurrent-use.md).
