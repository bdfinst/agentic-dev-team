"""Pytest tests for scripts/issue_deps.py (#614 / #572 Phase 3).

Mirrors the ``issue-deps.sh`` cases from ``issue_deps_tests.bats``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "issue_deps.py"
_FIX = _REPO_ROOT / "tests" / "fixtures" / "plans"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def test_diamond_maps_direct_predecessors() -> None:
    r = _run(str(_FIX / "diamond.md"))
    assert r.returncode == 0
    deps = json.loads(r.stdout)
    assert deps["A"] == []
    assert deps["B"] == ["A"]
    assert deps["D"] == ["B", "C"]


def test_dag_order_not_file_order() -> None:
    r = _run(str(_FIX / "dag-order.md"))
    assert r.returncode == 0
    deps = json.loads(r.stdout)
    assert deps["B"] == ["A"]
    assert deps["C"] == []


def test_single_slice_plan(tmp_path: Path) -> None:
    plan = tmp_path / "single.md"
    plan.write_text("### Slice 1: only\n**Depends-on:** none\n")
    r = _run(str(plan))
    assert r.returncode == 0
    deps = json.loads(r.stdout)
    assert deps["1"] == []
    assert len(deps) == 1


def test_cycle_propagates_nonzero() -> None:
    r = _run(str(_FIX / "cycle.md"))
    assert r.returncode != 0


def test_missing_file_arg_usage_error() -> None:
    r = _run()
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_nonexistent_file_usage_error(tmp_path: Path) -> None:
    r = _run(str(tmp_path / "nope.md"))
    assert r.returncode == 2


def test_unknown_slice_propagates() -> None:
    r = _run(str(_FIX / "unknown.md"))
    assert r.returncode != 0


def test_output_is_valid_json_and_map_of_lists() -> None:
    r = _run(str(_FIX / "diamond.md"))
    payload = json.loads(r.stdout)
    for sid, deps in payload.items():
        assert isinstance(sid, str)
        assert isinstance(deps, list)
        assert all(isinstance(d, str) for d in deps)
