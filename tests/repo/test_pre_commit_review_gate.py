"""#193 - the review gate binds staged CONTENT (via review-gate-hash.sh), so
editing a reviewed file after the gate is written re-blocks the commit. Both
the writer (/code-review step 9) and the reader (pre-commit-review.sh) use
the one shared helper, so they cannot diverge.

Ported from tests/repo/review_gate_hash_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "pre_commit_review.py"
GATEHASH = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "review_gate_hash.py"


@pytest.fixture
def work(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(tmp_path), env=hermetic_env, check=True
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


def _commit_hook(
    work: Path, hermetic_env: dict[str, str]
) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=str(work),
        env=hermetic_env,
        input=payload,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_gate(work: Path, hermetic_env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(GATEHASH)],
        cwd=str(work),
        env=hermetic_env,
        capture_output=True,
        text=True,
        check=True,
    )
    gate_path = work / ".claude" / "memory" / ".review-passed"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(result.stdout)


def _write_dispatch_evidence(work: Path) -> None:
    """Seed .claude/metrics/boundary-events.jsonl with 2 distinct genuine
    review-agent dispatches (#1461) — required, alongside the hash match,
    for the gate to accept a write since the dispatch-ledger corroboration
    hardening. See plugins/dev-team/tests/hooks/test_pre_commit_review.py
    for the full scenario coverage; this helper only seeds the passing case
    these repo-level gate tests need.

    Stamps `subject_hash` (#1461 security review) to the CURRENT staged
    content's hash — recomputed the same way `_write_gate` does — so this
    evidence corroborates THIS test's changeset, not an unrelated one."""
    result = subprocess.run(
        [sys.executable, str(GATEHASH)],
        cwd=str(work),
        capture_output=True,
        text=True,
        check=True,
    )
    subject_hash = result.stdout.strip()
    log = work / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Anchor the seeded dispatch timestamp to the gate file's OWN mtime — which
    # is exactly what the hook uses as the recency window's upper bound
    # (`before_ts`; see review_gate_corroboration.mtime_to_iso). The window is
    # inclusive-upper: `(before_ts - WINDOW_SECONDS, before_ts]`.
    #
    # Stamping wall-clock `now()` here was flaky under `pytest -n auto` (#1505):
    # this evidence is written just AFTER `_write_gate`, and both timestamps are
    # truncated to whole seconds. Under worker contention the gate-write and
    # this evidence-write can straddle a 1-second boundary, so `now()` floors to
    # one second LATER than the gate mtime — landing just past `before_ts` and
    # falling outside the window ("outside the 1800s window"). Seeding a fixed
    # margin BEFORE the gate mtime is immune to that boundary and to system
    # load, while staying far inside the 1800s window.
    gate_mtime = (work / ".claude" / "memory" / ".review-passed").stat().st_mtime
    stamp = (
        datetime.fromtimestamp(gate_mtime, tz=timezone.utc) - timedelta(seconds=60)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def test_gate_exact_staged_content_that_was_reviewed_commits_cleanly(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)
    _write_dispatch_evidence(work)
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 0
    assert not (
        work / ".claude" / "memory" / ".review-passed"
    ).is_file()  # consumed on success


def test_gate_editing_a_reviewed_files_content_reblocks_the_commit(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)  # reviewed a.ts @ v1
    (work / "a.ts").write_text("v2-unreviewed\n")
    _git(work, hermetic_env, "add", "a.ts")  # same path, new content
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 2  # FIXED: blocked (was 0 under path-only hash)
    assert "BLOCKED" in result.stdout + result.stderr


def test_gate_staging_an_extra_unreviewed_file_reblocks_the_commit(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.ts")
    _write_gate(work, hermetic_env)
    (work / "b.ts").write_text("new\n")
    _git(work, hermetic_env, "add", "b.ts")
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 2


def test_gate_writer_and_hook_compute_the_same_content_hash(
    work: Path, hermetic_env: dict[str, str]
) -> None:
    (work / "a.ts").write_text("line1\nline2\n")
    _git(work, hermetic_env, "add", "a.ts")
    # the helper's output (writer) must equal the hash the hook recomputes
    # (reader)
    _write_gate(work, hermetic_env)
    _write_dispatch_evidence(work)
    result = _commit_hook(work, hermetic_env)
    assert result.returncode == 0
