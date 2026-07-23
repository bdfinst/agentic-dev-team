"""Unit tests for scripts/build_rollback_point.py (issue #865).

Covers symbolic rollback-value resolution to a concrete SHA and
record/retrieve bookkeeping so a dead-end escalation (issue #864) can name
the exact revert boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import build_rollback_point  # noqa: E402

_GIT_SCRUB_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def _hermetic_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB_ENV_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=_hermetic_env(),
    )
    return result.stdout.strip()


def _init_repo(cwd: Path) -> None:
    _git(cwd, "init", "-q")
    _git(cwd, "config", "user.email", "test@test.com")
    _git(cwd, "config", "user.name", "Test")


# ---------------------------------------------------------------------------
# resolve_rollback_point
# ---------------------------------------------------------------------------


def test_resolve_slice_start_uses_supplied_anchor_ref(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    sha = _git(tmp_path, "rev-parse", "HEAD")

    resolved = build_rollback_point.resolve_rollback_point(
        "slice-start", repo_root=str(tmp_path), slice_start=sha
    )
    assert resolved == sha


def test_resolve_wave_start_and_plan_start_use_their_own_anchors(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    sha1 = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "b.txt").write_text("two\n")
    _git(tmp_path, "add", "b.txt")
    _git(tmp_path, "commit", "-m", "second")
    sha2 = _git(tmp_path, "rev-parse", "HEAD")

    assert (
        build_rollback_point.resolve_rollback_point(
            "wave-start",
            repo_root=str(tmp_path),
            wave_start=sha1,
            plan_start=sha2,
        )
        == sha1
    )
    assert (
        build_rollback_point.resolve_rollback_point(
            "plan-start",
            repo_root=str(tmp_path),
            wave_start=sha1,
            plan_start=sha2,
        )
        == sha2
    )


def test_resolve_explicit_ref_is_passed_through_to_git(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    _git(tmp_path, "tag", "v1")
    sha = _git(tmp_path, "rev-parse", "HEAD")

    resolved = build_rollback_point.resolve_rollback_point(
        "v1", repo_root=str(tmp_path)
    )
    assert resolved == sha


def test_resolve_symbolic_without_anchor_raises():
    with pytest.raises(ValueError):
        build_rollback_point.resolve_rollback_point("slice-start", repo_root=".")


def test_resolve_unresolvable_ref_raises(tmp_path):
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        build_rollback_point.resolve_rollback_point(
            "no-such-ref", repo_root=str(tmp_path)
        )


# ---------------------------------------------------------------------------
# record_rollback_point / get_rollback_point
# ---------------------------------------------------------------------------


def test_record_then_get_round_trips(tmp_path):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "slice-start", "abc123")
    entry = build_rollback_point.get_rollback_point(path, "1")
    assert entry["symbolic"] == "slice-start"
    assert entry["sha"] == "abc123"
    assert "recorded_at" in entry


def test_get_missing_slice_returns_none(tmp_path):
    path = tmp_path / "build-rollback.json"
    assert build_rollback_point.get_rollback_point(path, "nope") is None


def test_record_merges_with_existing_entries_for_other_slices(tmp_path):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "slice-start", "sha1")
    build_rollback_point.record_rollback_point(path, "2", "wave-start", "sha2")
    assert build_rollback_point.get_rollback_point(path, "1")["sha"] == "sha1"
    assert build_rollback_point.get_rollback_point(path, "2")["sha"] == "sha2"


# ---------------------------------------------------------------------------
# find_rollback_point_by_symbolic (issue #916 — Step 7 degenerate-base fallback)
# ---------------------------------------------------------------------------


_SCRIPT = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_rollback_point.py"


def test_find_by_symbolic_returns_the_matching_entry_regardless_of_slice(tmp_path):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "slice-start", "sha1")
    build_rollback_point.record_rollback_point(path, "2", "plan-start", "sha2")
    entry = build_rollback_point.find_rollback_point_by_symbolic(path, "plan-start")
    assert entry["sha"] == "sha2"


def test_find_by_symbolic_returns_none_when_no_slice_recorded_it(tmp_path):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "slice-start", "sha1")
    assert (
        build_rollback_point.find_rollback_point_by_symbolic(path, "plan-start") is None
    )


def test_find_by_symbolic_returns_none_for_a_missing_file(tmp_path):
    path = tmp_path / "does-not-exist.json"
    assert (
        build_rollback_point.find_rollback_point_by_symbolic(path, "plan-start") is None
    )


def test_find_by_symbolic_with_duplicate_symbolics_returns_the_first_by_insertion_order(
    tmp_path,
):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "sha-first")
    build_rollback_point.record_rollback_point(path, "2", "plan-start", "sha-second")
    entry = build_rollback_point.find_rollback_point_by_symbolic(path, "plan-start")
    assert entry["sha"] == "sha-first"


def test_find_by_symbolic_without_ancestor_check_accepts_any_matching_sha(tmp_path):
    # No repo_root/ancestor_of supplied -> unfiltered, even though "stale-sha"
    # is not a real commit anywhere.
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "stale-sha")
    entry = build_rollback_point.find_rollback_point_by_symbolic(path, "plan-start")
    assert entry["sha"] == "stale-sha"


def test_find_by_symbolic_with_ancestor_check_rejects_a_stale_sha_not_in_this_history(
    tmp_path,
):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    head = _git(tmp_path, "rev-parse", "HEAD")

    path = tmp_path / "build-rollback.json"
    # A plan-start entry recorded by an unrelated earlier build in the same
    # worktree, referencing a SHA that isn't part of this repo's history.
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "0" * 40)
    entry = build_rollback_point.find_rollback_point_by_symbolic(
        path, "plan-start", repo_root=str(tmp_path), ancestor_of=head
    )
    assert entry is None


def test_find_by_symbolic_with_ancestor_check_accepts_a_real_ancestor(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    plan_start_sha = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "b.txt").write_text("two\n")
    _git(tmp_path, "add", "b.txt")
    _git(tmp_path, "commit", "-m", "second")
    head = _git(tmp_path, "rev-parse", "HEAD")

    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "plan-start", plan_start_sha)
    entry = build_rollback_point.find_rollback_point_by_symbolic(
        path, "plan-start", repo_root=str(tmp_path), ancestor_of=head
    )
    assert entry["sha"] == plan_start_sha


def test_find_by_symbolic_with_ancestor_check_skips_a_stale_match_to_find_a_valid_one(
    tmp_path,
):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    valid_sha = _git(tmp_path, "rev-parse", "HEAD")

    path = tmp_path / "build-rollback.json"
    # Insertion order: stale entry first, valid entry second. The ancestry
    # filter must not stop at the first (stale) match.
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "1" * 40)
    build_rollback_point.record_rollback_point(path, "2", "plan-start", valid_sha)
    entry = build_rollback_point.find_rollback_point_by_symbolic(
        path, "plan-start", repo_root=str(tmp_path), ancestor_of=valid_sha
    )
    assert entry["sha"] == valid_sha


def test_cli_get_by_symbolic_prints_json_on_match(tmp_path):
    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "sha1")
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "get-by-symbolic",
            "--path",
            str(path),
            "--symbolic",
            "plan-start",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["sha"] == "sha1"


def test_cli_get_by_symbolic_exits_non_zero_on_no_match(tmp_path):
    path = tmp_path / "build-rollback.json"
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "get-by-symbolic",
            "--path",
            str(path),
            "--symbolic",
            "plan-start",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "plan-start" in result.stderr


def test_cli_get_by_symbolic_with_ancestor_of_rejects_a_stale_sha(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "first")
    head = _git(tmp_path, "rev-parse", "HEAD")

    path = tmp_path / "build-rollback.json"
    build_rollback_point.record_rollback_point(path, "1", "plan-start", "2" * 40)
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "get-by-symbolic",
            "--path",
            str(path),
            "--symbolic",
            "plan-start",
            "--repo",
            str(tmp_path),
            "--ancestor-of",
            head,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
