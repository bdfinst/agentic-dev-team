"""#109 Phase 1 — reproduce the multiplayer collision that REMAINS even after the
gate is content-bound (#193): two agents sharing ONE working tree share a
single `.review-passed` file and clobber each other's gate. The resolution is
operational, not a gate change — one git worktree per agent (see
plugins/dev-team/docs/concurrent-use.md). The content-binding behavior itself
is covered by test_review_gate_hash.py (plugins/dev-team/tests/hooks/).

Ported from tests/repo/multiplayer_collision_tests.bats (issue #671). Uses
pytest's `tmp_path` fixture for hermetic isolation instead of bats'
tests/lib/hermetic.bash (same intent: a scratch git repo the pre-commit
review hook can run `git commit` against without touching the parent
worktree's refs).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"
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
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=tmp_path, env=env, check=True
    )
    return tmp_path


def _commit_hook(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input='{"tool_input":{"command":"git commit -m x"}}',
        cwd=cwd,
        env=_git_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def _write_gate(cwd: Path) -> None:
    gate_path = cwd / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(_rgh.review_gate_hash(cwd=cwd))


def _write_dispatch_evidence(cwd: Path) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with 2 distinct genuine
    review-agent dispatches (#1461) — required, alongside the hash match,
    for the gate to accept a write since the dispatch-ledger corroboration
    hardening."""
    log = cwd / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
                    }
                )
                + "\n"
            )


def test_baseline_gate_written_for_current_staged_content_allows_commit(
    work: Path,
) -> None:
    (work / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=work, env=_git_env(), check=True)
    _write_gate(work)
    _write_dispatch_evidence(work)
    res = _commit_hook(work)
    assert res.returncode == 0, res.stdout + res.stderr


def test_collision_a_second_agent_overwriting_review_passed_falsely_blocks_the_first(
    work: Path,
) -> None:
    (work / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=work, env=_git_env(), check=True)
    _write_gate(work)  # agent A passed review for its staged content
    gate_path = work / ".claude" / "memory" / ".review-passed"
    gate_path.write_text(
        "a-different-agents-hash\n"
    )  # agent B (same tree) overwrote it
    res = _commit_hook(work)  # A commits its still-staged change
    assert res.returncode == 2  # ...and is blocked despite having passed
    assert "BLOCKED" in res.stdout
    # NOT fixed by content-hashing — two agents in one tree share one gate file.
    # Fix is operational: one worktree per agent (concurrent-use.md).
