"""Unit tests for scripts/build_rollback_point.py (issue #865).

Covers symbolic rollback-value resolution to a concrete SHA and
record/retrieve bookkeeping so a dead-end escalation (issue #864) can name
the exact revert boundary.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import build_rollback_point  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
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
