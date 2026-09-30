"""Unit tests for hooks/lib/build_state.py (#2177 slice 1)."""

from __future__ import annotations

import json
import os
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from build_state import BuildState, read_active_build_state


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
        "written_at": "2026-09-30T12:00:00Z",
        "test_files_staged": [],
        "plan_path": "plans/foo.md",
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "foo.md").write_text("# plan\n", encoding="utf-8")
    return tmp_path


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
    ["../../etc/passwd", "/etc/passwd", "plans/missing.md", "plans", "", None, 7, "a\x00b"],
)
def test_unsafe_or_missing_plan_path_is_dropped(repo, plan_path):
    _write_state(repo, _record(plan_path=plan_path))
    assert read_active_build_state(repo) == BuildState("test", "2.1", None)


def test_symlink_plan_path_escaping_repo_is_dropped(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("x", encoding="utf-8")
    os.symlink(outside, repo / "plans" / "link.md")
    _write_state(repo, _record(plan_path="plans/link.md"))
    assert read_active_build_state(repo).plan_path is None


def test_garbage_bytes_return_none(repo):
    path = _write_state(repo, "")
    path.write_bytes(b"\xff\xfe\x00garbage")
    assert read_active_build_state(repo) is None


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is not enforced for root / Windows",
)
def test_unreadable_record_returns_none(repo):
    path = _write_state(repo, _record())
    path.chmod(0)
    try:
        assert read_active_build_state(repo) is None
    finally:
        path.chmod(0o644)
