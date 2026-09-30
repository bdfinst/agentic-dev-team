"""Unit tests for hooks/lib/build_state.py (#2177 slice 1)."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from build_state import (
    STALE_AFTER_SECONDS,
    BuildState,
    read_active_build_state,
)
from test_file_classify import STALE_AFTER_SECONDS as CLASSIFY_STALE


def _fresh() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_state(root, content):
    path = root / ".claude" / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    path.write_text(content, encoding="utf-8")
    return path


def _record(**overrides):
    base = {
        "phase": "test",
        "step": "2.1",
        "written_at": _fresh(),
        "test_files_staged": [],
        "plan_path": "plans/foo.md",
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "plans").mkdir(parents=True)
    (root / "plans" / "foo.md").write_text("# plan\n", encoding="utf-8")
    return root


def test_record_with_plan_path_is_active(repo):
    _write_state(repo, _record())
    assert read_active_build_state(repo) == BuildState("test", "2.1", "plans/foo.md")


def test_absent_record_means_no_state(repo):
    assert read_active_build_state(repo) is None


@pytest.mark.parametrize("content", ["", "   \n", "{}", "[]", '"x"', "null"])
def test_cleared_shapes_mean_no_state(repo, content):
    _write_state(repo, content)
    assert read_active_build_state(repo) is None


@pytest.mark.parametrize(
    "override",
    [{"phase": ""}, {"step": ""}, {"phase": 3}, {"step": None}],
)
def test_missing_or_non_string_phase_step_is_cleared(repo, override):
    _write_state(repo, _record(**override))
    assert read_active_build_state(repo) is None


def test_record_without_plan_path_is_phase_only(repo):
    rec = _record(phase="implement", step="1.1")
    del rec["plan_path"]
    _write_state(repo, rec)
    assert read_active_build_state(repo) == BuildState("implement", "1.1", None)


@pytest.mark.parametrize(
    "plan_path",
    ["/etc/passwd", "plans/missing.md", "plans", "", None, 7, "a\x00b"],
)
def test_unsafe_or_missing_plan_path_is_dropped(repo, plan_path):
    _write_state(repo, _record(plan_path=plan_path))
    assert read_active_build_state(repo) == BuildState("test", "2.1", None)


def test_real_file_outside_the_project_is_omitted_via_dotdot(tmp_path, repo):
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")  # sibling of repo/
    _write_state(repo, _record(plan_path="../secret.md"))
    assert read_active_build_state(repo) == BuildState("test", "2.1", None)


def test_real_absolute_file_outside_the_project_is_omitted(tmp_path, repo):
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    _write_state(repo, _record(plan_path=str(outside)))
    assert read_active_build_state(repo).plan_path is None


def test_symlink_plan_path_escaping_repo_is_dropped(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("x", encoding="utf-8")
    os.symlink(outside, repo / "plans" / "link.md")
    _write_state(repo, _record(plan_path="plans/link.md"))
    assert read_active_build_state(repo).plan_path is None


def test_symlink_loop_plan_path_is_dropped_without_raising(repo):
    os.symlink("b.md", repo / "plans" / "a.md")
    os.symlink("a.md", repo / "plans" / "b.md")
    _write_state(repo, _record(plan_path="plans/a.md"))
    assert read_active_build_state(repo) == BuildState("test", "2.1", None)


def test_symlink_loop_state_file_is_none(repo):
    mem = repo / ".claude" / "memory"
    mem.mkdir(parents=True)
    os.symlink("build-phase.json", mem / "build-phase.json")
    assert read_active_build_state(repo) is None


def test_garbage_bytes_return_none(repo):
    path = _write_state(repo, "")
    path.write_bytes(b"\xff\xfe\x00garbage")
    assert read_active_build_state(repo) is None


def test_state_path_that_is_a_directory_returns_none(repo):
    (repo / ".claude" / "memory" / "build-phase.json").mkdir(parents=True)
    assert read_active_build_state(repo) is None


def test_deeply_nested_json_is_fail_open(repo):
    _write_state(repo, "[" * 200_000)
    assert read_active_build_state(repo) is None


def test_staleness_threshold_matches_the_refactor_guards():
    assert STALE_AFTER_SECONDS == CLASSIFY_STALE


def test_stale_record_is_ignored_and_fresh_one_is_kept(repo):
    now = time.time()
    written = datetime.fromtimestamp(now - STALE_AFTER_SECONDS - 60, timezone.utc).isoformat()
    _write_state(repo, _record(written_at=written))
    assert read_active_build_state(repo, now=now) is None
    fresh = datetime.fromtimestamp(now - STALE_AFTER_SECONDS + 60, timezone.utc).isoformat()
    _write_state(repo, _record(written_at=fresh))
    assert read_active_build_state(repo, now=now) is not None


@pytest.mark.parametrize("written_at", [None, "", "yesterday", 5])
def test_missing_or_unparseable_written_at_is_cleared(repo, written_at):
    _write_state(repo, _record(written_at=written_at))
    assert read_active_build_state(repo) is None


def test_z_suffix_timestamps_parse(repo):
    now = time.time()
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_state(repo, _record(written_at=stamp))
    assert read_active_build_state(repo, now=now) is not None
