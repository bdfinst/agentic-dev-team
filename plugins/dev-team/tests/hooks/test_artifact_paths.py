"""Unit tests for hooks/lib/artifact_paths.py (Slice 4, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

Covers project_root() git-root resolution with cwd fallback.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import pytest

import artifact_paths  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def _init_repo(path: Path) -> dict:
    env = hermetic_git_env(home=path)
    subprocess.run(["git", "init", "-q"], cwd=path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, env=env, check=True)
    return env


def test_project_root_resolves_git_toplevel(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.project_root(start=tmp_path) == tmp_path.resolve()


def test_project_root_falls_back_to_start_outside_a_repo(tmp_path: Path) -> None:
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    assert artifact_paths.project_root(start=non_repo) == non_repo


def test_project_root_resolves_from_a_subdirectory(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sub = tmp_path / "sub" / "deeper"
    sub.mkdir(parents=True)
    assert artifact_paths.project_root(start=sub) == tmp_path.resolve()


# --- category directory accessors -----------------------------------------


def test_metrics_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.metrics_dir(tmp_path) == tmp_path.resolve() / ".claude" / "metrics"


def test_memory_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.memory_dir(tmp_path) == tmp_path.resolve() / ".claude" / "memory"


def test_plans_dir_resolves_under_dot_claude(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert artifact_paths.plans_dir(tmp_path) == tmp_path.resolve() / ".claude" / "plans"


# --- resolve_file() ---------------------------------------------------------


def test_resolve_file_migrates_an_untracked_legacy_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    legacy = tmp_path / "metrics" / "cost-metering.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy-content\n")

    result = artifact_paths.resolve_file("metrics", "cost-metering.jsonl", tmp_path)

    expected = tmp_path.resolve() / ".claude" / "metrics" / "cost-metering.jsonl"
    assert result == expected
    assert expected.read_text() == "legacy-content\n"
    assert not legacy.exists()


def test_resolve_file_leaves_a_git_tracked_legacy_file_in_place(tmp_path: Path) -> None:
    env = _init_repo(tmp_path)
    legacy = tmp_path / "memory" / "decisions.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("tracked-content\n")
    subprocess.run(["git", "add", "memory/decisions.md"], cwd=tmp_path, env=env, check=True)

    result = artifact_paths.resolve_file("memory", "decisions.md", tmp_path)

    expected = tmp_path.resolve() / ".claude" / "memory" / "decisions.md"
    assert result == expected
    assert legacy.exists()
    assert legacy.read_text() == "tracked-content\n"
    assert not expected.exists()


def test_resolve_file_migrate_false_has_no_side_effects(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    legacy = tmp_path / "metrics" / "cost-metering.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy-content\n")

    result = artifact_paths.resolve_file(
        "metrics", "cost-metering.jsonl", tmp_path, migrate=False
    )

    expected = tmp_path.resolve() / ".claude" / "metrics" / "cost-metering.jsonl"
    assert result == expected
    assert legacy.exists()
    assert legacy.read_text() == "legacy-content\n"
    assert not (tmp_path / ".claude").exists()


def test_resolve_file_no_legacy_file_returns_new_path_only(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = artifact_paths.resolve_file("metrics", "cost-metering.jsonl", tmp_path)
    expected = tmp_path.resolve() / ".claude" / "metrics" / "cost-metering.jsonl"
    assert result == expected
    assert not expected.exists()


def test_resolve_file_refuses_to_follow_a_symlinked_legacy_path(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("should not be moved\n")
    legacy_dir = tmp_path / "metrics"
    legacy_dir.mkdir()
    legacy_link = legacy_dir / "cost-metering.jsonl"
    legacy_link.symlink_to(real_target)

    result = artifact_paths.resolve_file("metrics", "cost-metering.jsonl", tmp_path)

    expected = tmp_path.resolve() / ".claude" / "metrics" / "cost-metering.jsonl"
    assert result == expected
    assert not expected.exists()
    assert legacy_link.is_symlink()
    assert real_target.read_text() == "should not be moved\n"


def test_resolve_file_fails_closed_when_git_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    legacy = tmp_path / "metrics" / "cost-metering.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy-content\n")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(artifact_paths.subprocess, "run", _raise)

    result = artifact_paths.resolve_file("metrics", "cost-metering.jsonl", tmp_path)

    expected = tmp_path.resolve() / ".claude" / "metrics" / "cost-metering.jsonl"
    assert result == expected
    assert legacy.exists()
    assert legacy.read_text() == "legacy-content\n"
    assert not expected.exists()


@pytest.mark.parametrize("bad_category", ["..", ".", "", "a/b", "a\0b"])
def test_resolve_file_rejects_path_traversal_in_category(
    tmp_path: Path, bad_category: str
) -> None:
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        artifact_paths.resolve_file(bad_category, "x.jsonl", tmp_path)


@pytest.mark.parametrize("bad_filename", ["..", ".", "", "../../../../etc/passwd", "a/b"])
def test_resolve_file_rejects_path_traversal_in_filename(
    tmp_path: Path, bad_filename: str
) -> None:
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        artifact_paths.resolve_file("metrics", bad_filename, tmp_path)


# --- category_dir() ---------------------------------------------------------


def test_category_dir_joins_subpath_without_side_effects(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = artifact_paths.category_dir("memory", tmp_path) / "test-improve" / "slug-a"
    expected = tmp_path.resolve() / ".claude" / "memory" / "test-improve" / "slug-a"
    assert result == expected
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "memory").exists()


# --- migrate_dir() -----------------------------------------------------------


def test_migrate_dir_moves_every_untracked_file_in_a_multi_slug_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    for slug in ("slug-a", "slug-b"):
        for phase in ("phase-0.md", "phase-1.md"):
            f = tmp_path / "memory" / "test-improve" / slug / phase
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"{slug}/{phase}\n")

    artifact_paths.migrate_dir("memory", "test-improve", tmp_path)

    new_root = tmp_path.resolve() / ".claude" / "memory" / "test-improve"
    for slug in ("slug-a", "slug-b"):
        for phase in ("phase-0.md", "phase-1.md"):
            moved = new_root / slug / phase
            assert moved.read_text() == f"{slug}/{phase}\n"
            assert not (tmp_path / "memory" / "test-improve" / slug / phase).exists()


def test_migrate_dir_leaves_a_git_tracked_file_in_place(tmp_path: Path) -> None:
    env = _init_repo(tmp_path)
    tracked = tmp_path / "memory" / "test-improve" / "slug-a" / "notes.md"
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("tracked\n")
    subprocess.run(
        ["git", "add", "memory/test-improve/slug-a/notes.md"],
        cwd=tmp_path,
        env=env,
        check=True,
    )
    untracked = tmp_path / "memory" / "test-improve" / "slug-a" / "phase-0.md"
    untracked.write_text("untracked\n")

    artifact_paths.migrate_dir("memory", "test-improve", tmp_path)

    assert tracked.exists()
    assert tracked.read_text() == "tracked\n"
    new_root = tmp_path.resolve() / ".claude" / "memory" / "test-improve" / "slug-a"
    assert not (new_root / "notes.md").exists()
    assert (new_root / "phase-0.md").read_text() == "untracked\n"
    assert not untracked.exists()


def test_migrate_dir_skips_an_excluded_basename_even_if_untracked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    backlog = tmp_path / "memory" / "test-improve" / "slug-a" / "refactor-backlog.md"
    backlog.parent.mkdir(parents=True, exist_ok=True)
    backlog.write_text("backlog\n")
    sibling = tmp_path / "memory" / "test-improve" / "slug-a" / "phase-0.md"
    sibling.write_text("sibling\n")

    artifact_paths.migrate_dir(
        "memory", "test-improve", tmp_path, exclude={"refactor-backlog.md"}
    )

    assert backlog.exists()
    assert backlog.read_text() == "backlog\n"
    new_root = tmp_path.resolve() / ".claude" / "memory" / "test-improve" / "slug-a"
    assert not (new_root / "refactor-backlog.md").exists()
    assert (new_root / "phase-0.md").read_text() == "sibling\n"
    assert not sibling.exists()


def test_migrate_dir_no_legacy_tree_is_a_no_op(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    artifact_paths.migrate_dir("memory", "test-improve", tmp_path)
    assert not (tmp_path / ".claude").exists()


def test_migrate_dir_skips_a_symlinked_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    real_target = tmp_path / "elsewhere.txt"
    real_target.write_text("should not be moved\n")
    legacy_dir = tmp_path / "memory" / "test-improve" / "slug-a"
    legacy_dir.mkdir(parents=True)
    legacy_link = legacy_dir / "phase-0.md"
    legacy_link.symlink_to(real_target)

    artifact_paths.migrate_dir("memory", "test-improve", tmp_path)

    new_root = tmp_path.resolve() / ".claude" / "memory" / "test-improve" / "slug-a"
    assert not (new_root / "phase-0.md").exists()
    assert legacy_link.is_symlink()
    assert real_target.read_text() == "should not be moved\n"


@pytest.mark.parametrize("bad_category", ["..", ".", "", "a/b"])
def test_migrate_dir_rejects_path_traversal_in_category(
    tmp_path: Path, bad_category: str
) -> None:
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        artifact_paths.migrate_dir(bad_category, "test-improve", tmp_path)


@pytest.mark.parametrize("bad_subpath", ["..", ".", "", "a/b"])
def test_migrate_dir_rejects_path_traversal_in_subpath(
    tmp_path: Path, bad_subpath: str
) -> None:
    _init_repo(tmp_path)
    with pytest.raises(ValueError):
        artifact_paths.migrate_dir("memory", bad_subpath, tmp_path)


# --- dev_team_reports_dir() --------------------------------------------------


def test_dev_team_reports_dir_resolves_with_no_side_effects(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = artifact_paths.dev_team_reports_dir(tmp_path)
    expected = tmp_path.resolve() / ".dev-team-reports"
    assert result == expected
    assert not expected.exists()


def test_dev_team_reports_dir_resolves_from_a_subdirectory(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    result = artifact_paths.dev_team_reports_dir(sub)
    expected = tmp_path.resolve() / ".dev-team-reports"
    assert result == expected
