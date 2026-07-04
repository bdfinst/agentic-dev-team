"""Slice 2 (build-worktree-inherits-caller-head): build_wave_reconcile.py
must carry the caller's pre-fanout WIP commits (docs/specs/<slug>.md,
plans/<slug>.md) into the reconciled integration branch's ancestry.
Reconciling by branching `--into` fresh off `--base` discards any commit
made on the integration branch after slice branches diverged from it but
before reconcile ran.

Behavior under test (mirrors the plan's Slice 2 Gherkin):

  Feature: build_wave_reconcile.py carries caller WIP commits into the
    integration branch

    Scenario: WIP commit on integration branch is preserved
      Given an integration branch with a WIP commit (spec+plan) not on
        origin/main
      And two slice branches created from that integration branch
      When I run build_wave_reconcile.py
        --into <integration> --base origin/main
        --test-cmd "true" <slice-1> <slice-2>
      Then the merge succeeds
      And "git log --format=%H <integration>" contains the WIP commit's sha
      And the reconciled tip's tree contains the WIP commit's files

    Scenario: WIP commit is preserved even when a slice adds a sibling file
      Given the WIP commit added docs/specs/foo.md
      And slice 1 adds an unrelated file docs/specs/bar.md
      When reconcile runs
      Then both files are present at the reconciled tip
      And no manual conflict resolution was required

    Scenario: same-file conflict resolution is unchanged
      Given the WIP commit modified plans/foo.md
      And slice 1 also modified plans/foo.md at conflicting lines
      When reconcile runs
      Then the pre-existing conflict-resolution behavior applies unchanged
        (out of scope for this fix)

Uses pytest's `tmp_path` fixture for the hermetic git repo (replaces
`mktemp -d` + `rm -rf`) and an explicitly scrubbed subprocess env (mirrors
tests/lib/hermetic.bash's GIT_DIR/GIT_CONFIG_GLOBAL/etc. scrubbing —
issue #546) instead of `load '../lib/hermetic'`.

Ported from tests/skills/build_wave_reconcile_wip_preservation_tests.bats
(issue #674).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "build_wave_reconcile.py"


def _hermetic_env() -> dict:
    env = dict(os.environ)
    for var in (
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_PREFIX",
        "GIT_REFLOG_ACTION",
    ):
        env.pop(var, None)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git(repo: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_reconcile(repo: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _setup_repo(repo: Path, env: dict) -> str:
    """Mirrors the bats `setup()` fixture: init repo, seed origin/main,
    integration branch, two divergent slice branches, and a WIP commit
    landing on integration after the slices diverged. Returns the WIP
    commit's sha."""
    _git(repo, "init", "-q", env=env)
    _git(repo, "config", "user.email", "t@t.com", env=env)
    _git(repo, "config", "user.name", "T", env=env)
    _git(repo, "checkout", "-q", "-b", "main", env=env)

    (repo / "README.md").write_text("readme\n")
    _git(repo, "add", "README.md", env=env)
    _git(repo, "commit", "-q", "-m", "init", env=env)

    # Simulate origin/main as a separate ref pointing at the same init
    # commit.
    _git(repo, "update-ref", "refs/remotes/origin/main", "main", env=env)

    # integration branch, diverged from origin/main before any WIP commit.
    _git(repo, "checkout", "-q", "-b", "integration", "main", env=env)

    # Slice branches diverge from integration BEFORE the WIP commit lands.
    _git(repo, "checkout", "-q", "-b", "slice-1", "integration", env=env)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "slice1.txt").write_text("slice-1 work\n")
    _git(repo, "add", "src/slice1.txt", env=env)
    _git(repo, "commit", "-q", "-m", "slice-1: add feature 1", env=env)

    _git(repo, "checkout", "-q", "-b", "slice-2", "integration", env=env)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "slice2.txt").write_text("slice-2 work\n")
    _git(repo, "add", "src/slice2.txt", env=env)
    _git(repo, "commit", "-q", "-m", "slice-2: add feature 2", env=env)

    # WIP commit lands on integration AFTER slice branches diverged.
    _git(repo, "checkout", "-q", "integration", env=env)
    (repo / "docs" / "specs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "specs" / "foo.md").write_text("wip spec\n")
    _git(repo, "add", "docs/specs/foo.md", env=env)
    _git(repo, "commit", "-q", "-m", "wip: spec+plan for foo", env=env)
    return _git(repo, "rev-parse", "HEAD", env=env).stdout.strip()


# ---------------------------------------------------------------------------
# 2.1a — WIP commit on integration branch is preserved (base RED per the plan)
# ---------------------------------------------------------------------------


def test_2_1a_wip_commit_sha_survives_reconcile_into_integration(tmp_path):
    env = _hermetic_env()
    wip_sha = _setup_repo(tmp_path, env)

    result = _run_reconcile(
        tmp_path,
        env,
        "--into",
        "integration",
        "--base",
        "origin/main",
        "--test-cmd",
        "true",
        "slice-1",
        "slice-2",
    )
    assert result.returncode == 0

    log = _git(tmp_path, "log", "--format=%H", "integration", env=env)
    assert log.returncode == 0
    assert wip_sha in log.stdout


def test_2_1b_wip_commits_file_is_present_at_the_reconciled_tip(tmp_path):
    env = _hermetic_env()
    _setup_repo(tmp_path, env)

    result = _run_reconcile(
        tmp_path,
        env,
        "--into",
        "integration",
        "--base",
        "origin/main",
        "--test-cmd",
        "true",
        "slice-1",
        "slice-2",
    )
    assert result.returncode == 0

    assert (tmp_path / "docs" / "specs" / "foo.md").is_file()
    shown = _git(tmp_path, "show", "integration:docs/specs/foo.md", env=env)
    assert shown.returncode == 0
    assert shown.stdout.strip() == "wip spec"


# ---------------------------------------------------------------------------
# 2.1c — stricter probe: a second WIP commit made BETWEEN wave dispatches
# (i.e. after slice branches already exist, simulating a caller who commits
# more spec/plan work while wave 1 subagents are running) must also survive.
# This is the escalated RED the plan requires if the base scenario already
# passes on today's script.
# ---------------------------------------------------------------------------


def test_2_1c_a_second_wip_commit_made_between_wave_dispatches_also_survives(tmp_path):
    env = _hermetic_env()
    wip_sha = _setup_repo(tmp_path, env)

    _git(tmp_path, "checkout", "-q", "integration", env=env)
    (tmp_path / "plans").mkdir(parents=True, exist_ok=True)
    (tmp_path / "plans" / "foo.md").write_text("wip plan\n")
    _git(tmp_path, "add", "plans/foo.md", env=env)
    _git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "wip: second commit, made between wave dispatches",
        env=env,
    )
    second_wip_sha = _git(tmp_path, "rev-parse", "HEAD", env=env).stdout.strip()

    result = _run_reconcile(
        tmp_path,
        env,
        "--into",
        "integration",
        "--base",
        "origin/main",
        "--test-cmd",
        "true",
        "slice-1",
        "slice-2",
    )
    assert result.returncode == 0

    log = _git(tmp_path, "log", "--format=%H", "integration", env=env)
    assert log.returncode == 0
    assert wip_sha in log.stdout
    assert second_wip_sha in log.stdout

    assert (tmp_path / "plans" / "foo.md").is_file()
    shown = _git(tmp_path, "show", "integration:plans/foo.md", env=env)
    assert shown.returncode == 0
    assert shown.stdout.strip() == "wip plan"


# ---------------------------------------------------------------------------
# 2.1d — sibling-file case: WIP file and a slice-added file both survive
# ---------------------------------------------------------------------------


def test_2_1d_wip_file_and_slice_added_sibling_file_both_present_no_manual_conflict(
    tmp_path,
):
    env = _hermetic_env()
    _setup_repo(tmp_path, env)

    _git(tmp_path, "checkout", "-q", "slice-1", env=env)
    (tmp_path / "docs" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "specs" / "bar.md").write_text("slice-1 sibling spec\n")
    _git(tmp_path, "add", "docs/specs/bar.md", env=env)
    _git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "slice-1: add sibling spec docs/specs/bar.md",
        env=env,
    )

    result = _run_reconcile(
        tmp_path,
        env,
        "--into",
        "integration",
        "--base",
        "origin/main",
        "--test-cmd",
        "true",
        "slice-1",
        "slice-2",
    )
    assert result.returncode == 0

    foo = _git(tmp_path, "show", "integration:docs/specs/foo.md", env=env)
    assert foo.returncode == 0
    assert foo.stdout.strip() == "wip spec"

    bar = _git(tmp_path, "show", "integration:docs/specs/bar.md", env=env)
    assert bar.returncode == 0
    assert bar.stdout.strip() == "slice-1 sibling spec"


# ---------------------------------------------------------------------------
# 2.1e — same-file conflict resolution is unchanged (out of scope; regression
# guard that the existing halt-and-abort behavior still fires)
# ---------------------------------------------------------------------------


def test_2_1e_same_file_conflict_between_wip_commit_and_a_slice_still_halts_the_merge(
    tmp_path,
):
    env = _hermetic_env()
    _setup_repo(tmp_path, env)

    _git(tmp_path, "checkout", "-q", "slice-1", env=env)
    (tmp_path / "docs" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "specs" / "foo.md").write_text("slice-1 conflicting edit\n")
    _git(tmp_path, "add", "docs/specs/foo.md", env=env)
    _git(
        tmp_path,
        "commit",
        "-q",
        "-m",
        "slice-1: conflicting edit to docs/specs/foo.md",
        env=env,
    )

    result = _run_reconcile(
        tmp_path,
        env,
        "--into",
        "integration",
        "--base",
        "origin/main",
        "--test-cmd",
        "true",
        "slice-1",
        "slice-2",
    )
    # bats' `run` merges stdout+stderr into $output; the script writes this
    # particular message to stderr.
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "CONFLICT" in combined
    assert "docs/specs/foo.md" in combined
