"""#2037 — `.husky/pre-commit` (the real git-native pre-commit gate) emits a
POSITIVE `gate_ran` boundary event, carrying its own verdict, at every exit
point — not just when it blocks.

Why this file, not `plugins/dev-team/tests/hooks/`: `.husky/pre-commit` is
repo-root tooling (a real POSIX-sh git hook), not shipped plugin code — same
classification as the other `.husky/*` scripts this test tree already
covers (`test_pre_pr_review_husky_independence.py`).

Covers the acceptance criteria from issue #2037:
  - a gate that runs and blocks records the blocking verdict
    (`test_pre_commit_blocks_and_records_the_block_verdict_on_dirty_corpus`
    — the DELIBERATE-FAILURE test: proves the gate actually rejects a
    commit it should reject, per the repo's own "make it fail on purpose
    once before you trust it" rule);
  - a gate that runs clean records that too
    (`test_pre_commit_allows_and_records_the_allow_verdict_on_a_clean_commit`);
  - a hook whose OWN logic errors is distinguishable from one that ran clean
    (`test_pre_commit_records_the_errored_verdict_when_the_corpus_check_itself_cannot_run`);
  - an unprovisioned worktree (no `node_modules/.bin/husky`, so git's
    `core.hooksPath` either isn't set or points at an empty/missing
    directory) never invokes this script at all — `gate_absent`'s real-world
    precondition
    (`test_git_commit_succeeds_silently_when_husky_is_unprovisioned`).

See `tests/repo/test_gate_ran_correlation.py` for how a `gate_ran` event
recorded here gets correlated back to a specific commit-attempt Bash record
in `session_report.py`'s digest — that is where "no correlated
event -> gate_absent" is actually pinned as an observable classification,
not just as an absence of activity.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

HUSKY_PRE_COMMIT = REPO_ROOT / ".husky" / "pre-commit"
_LIB_SRC = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"


def _git(work: Path, hermetic_env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(work),
        env=hermetic_env,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def gated_repo(tmp_path: Path, hermetic_env: dict[str, str]) -> Path:
    """A real git repo carrying just enough of `plugins/dev-team/hooks/lib/`
    for `.husky/pre-commit` to run against — the real `boundary_events.py`
    (+ its own `artifact_paths.py`/`atomic_state.py` dependencies) and the
    real `knowledge_index_paths.py` (so the corpus-dirty regex this test
    exercises is the genuine one, not a hand-rolled stand-in). Only
    `build_knowledge_index.py` is a stub — an instant no-op — since these
    tests are not exercising the real index builder, only the gate's own
    pass/block/error classification and its `gate_ran` emission."""
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, hermetic_env, "init", "-q", "-b", "main")
    _git(work, hermetic_env, "config", "user.email", "t@t.dev")
    _git(work, hermetic_env, "config", "user.name", "tester")

    lib_dst = work / "plugins" / "dev-team" / "hooks" / "lib"
    lib_dst.mkdir(parents=True)
    for name in (
        "boundary_events.py",
        "artifact_paths.py",
        "atomic_state.py",
        "knowledge_index_paths.py",
        "plugin_version.py",
    ):
        shutil.copy(_LIB_SRC / name, lib_dst / name)
    (lib_dst / "build_knowledge_index.py").write_text(
        "from pathlib import Path\n"
        "Path('plugins/dev-team/knowledge/index.json').write_text('{}')\n"
    )
    (work / "plugins" / "dev-team" / "knowledge").mkdir(parents=True)

    # Stub `node_modules/.bin/lint-staged` so `npx --no-install lint-staged`
    # (step 2 of the real script) resolves to something instead of failing
    # on a missing package — these tests exercise the gate's OWN
    # classification, not lint-staged itself.
    bin_dir = work / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    lint_staged_stub = bin_dir / "lint-staged"
    lint_staged_stub.write_text("#!/usr/bin/env sh\nexit 0\n")
    lint_staged_stub.chmod(0o755)
    (work / "package.json").write_text('{"name": "fixture", "private": true}\n')

    (work / "base.txt").write_text("base\n")
    _git(work, hermetic_env, "add", "-A")
    result = _git(work, hermetic_env, "commit", "-q", "-m", "initial")
    assert result.returncode == 0, result.stdout + result.stderr
    return work


def _run_pre_commit(work: Path, hermetic_env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(HUSKY_PRE_COMMIT)],
        cwd=str(work),
        env=hermetic_env,
        check=False,
        capture_output=True,
        text=True,
    )


def _gate_ran_events(work: Path) -> list[dict]:
    log = work / ".claude" / "metrics" / "boundary-events.jsonl"
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_pre_commit_allows_and_records_the_allow_verdict_on_a_clean_commit(
    gated_repo: Path, hermetic_env: dict[str, str]
) -> None:
    (gated_repo / "clean.txt").write_text("v1\n")
    _git(gated_repo, hermetic_env, "add", "clean.txt")

    result = _run_pre_commit(gated_repo, hermetic_env)

    assert result.returncode == 0, result.stdout + result.stderr
    events = _gate_ran_events(gated_repo)
    assert len(events) == 1
    assert events[0]["hook"] == "pre-commit-gate"
    assert events[0]["decision"] == "record"
    assert events[0]["matched_rule"] == "gate-ran-allow"


def test_pre_commit_blocks_and_records_the_block_verdict_on_dirty_corpus(
    gated_repo: Path, hermetic_env: dict[str, str]
) -> None:
    """DELIBERATE-FAILURE TEST (#2009/#2037's own ask): proves the gate
    actually rejects a commit it should reject, not merely that it emits a
    record. An untracked `plugins/dev-team/knowledge/*.md` file — a real
    corpus path per `knowledge_index_paths.CORPUS_REGEX` — makes the
    rebuilt index.json diverge from what this commit would contain, which
    is exactly the condition `.husky/pre-commit` exists to catch."""
    (gated_repo / "plugins" / "dev-team" / "knowledge" / "untracked.md").write_text(
        "# dirty corpus file\n"
    )
    (gated_repo / "clean.txt").write_text("v2\n")
    _git(gated_repo, hermetic_env, "add", "clean.txt")

    result = _run_pre_commit(gated_repo, hermetic_env)

    assert result.returncode != 0
    assert "stage or stash them first" in result.stderr
    events = _gate_ran_events(gated_repo)
    assert len(events) == 1
    assert events[0]["matched_rule"] == "gate-ran-block"


def test_pre_commit_records_the_errored_verdict_when_the_corpus_check_itself_cannot_run(
    gated_repo: Path, hermetic_env: dict[str, str]
) -> None:
    """A hook whose own logic errors must be distinguishable from one that
    ran clean (#2037 acceptance criterion). Simulated by removing the
    corpus-dirty check's own dependency
    (`knowledge_index_paths.filter_corpus_paths`) — the check's inline
    Python fails to import it and the script correctly reports "errored",
    not "allow" or "block"."""
    (gated_repo / "plugins" / "dev-team" / "hooks" / "lib" / "knowledge_index_paths.py").unlink()
    (gated_repo / "clean.txt").write_text("v3\n")
    _git(gated_repo, hermetic_env, "add", "clean.txt")

    result = _run_pre_commit(gated_repo, hermetic_env)

    assert result.returncode != 0
    assert "corpus-dirty check failed to run" in result.stderr
    events = _gate_ran_events(gated_repo)
    assert len(events) == 1
    assert events[0]["matched_rule"] == "gate-ran-errored"


def test_git_commit_succeeds_silently_when_husky_is_unprovisioned(
    tmp_path: Path, hermetic_env: dict[str, str]
) -> None:
    """`gate_absent`'s real-world precondition: an unprovisioned worktree
    (no `node_modules/.bin/husky`, so `npm run prepare` never ran) has no
    `core.hooksPath` override at all — a bare `git commit` succeeds with
    NOTHING invoking `.husky/pre-commit`, and consequently no `gate_ran`
    event is ever recorded. Mirrors
    `test_pre_pr_review_husky_independence.py`'s missing-`core.hooksPath`
    scenario for the git-native (not Claude-Code-level) gate."""
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, hermetic_env, "init", "-q", "-b", "main")
    _git(work, hermetic_env, "config", "user.email", "t@t.dev")
    _git(work, hermetic_env, "config", "user.name", "tester")
    assert (
        _git(work, hermetic_env, "config", "--get", "core.hooksPath").returncode != 0
    )  # unset — the default, unprovisioned state

    (work / "a.txt").write_text("v1\n")
    _git(work, hermetic_env, "add", "a.txt")
    result = _git(work, hermetic_env, "commit", "-q", "-m", "initial")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (work / ".claude" / "metrics" / "boundary-events.jsonl").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
