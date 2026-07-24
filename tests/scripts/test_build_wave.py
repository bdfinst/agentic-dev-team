"""Pytest tests for scripts/build_wave.py (#611 / #572 Phase 3).

Mirrors the ``build-wave.sh`` cases from
``tests/scripts/build_wave_tests.bats``. The parity harness under
``plugins/dev-team/tests/hooks/parity/`` gates byte-equivalence between
`.sh` and `.py`; this suite adds targeted assertions on the port's
observable JSON contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT_PY = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "build_wave.py"
_FIX = _REPO_ROOT / "tests" / "fixtures" / "plans"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def test_usage_when_no_arg() -> None:
    r = _run()
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_usage_when_file_missing(tmp_path: Path) -> None:
    r = _run(str(tmp_path / "nonexistent.md"))
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_diamond_emits_schedule() -> None:
    r = _run(str(_FIX / "diamond.md"))
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["schema"] == "build-wave/v1"
    assert [w["members"] for w in payload["waves"]] == [["A"], ["B", "C"], ["D"]]
    # Reconcile order is sorted for determinism.
    assert payload["waves"][1]["reconcile_order"] == ["B", "C"]
    assert payload["collisions"] == []


def test_collision_refused_with_stderr_message() -> None:
    r = _run(str(_FIX / "collision.md"))
    assert r.returncode != 0
    assert "collision" in r.stderr
    # The collision message names the file both slices touch.
    assert "shared.ts" in r.stderr


def test_cycle_propagates_exit_code() -> None:
    r = _run(str(_FIX / "cycle.md"))
    assert r.returncode == 2
    assert "cycle" in r.stderr.lower() or "cyclic" in r.stderr.lower()


def test_missing_depends_on() -> None:
    r = _run(str(_FIX / "missing.md"))
    assert r.returncode == 2
    assert "Depends-on" in r.stderr


def test_unknown_dependency() -> None:
    r = _run(str(_FIX / "unknown.md"))
    assert r.returncode == 2
    assert "unknown" in r.stderr.lower()


def test_linear_and_nodeps_shape_is_wave1_only_for_no_deps() -> None:
    r = _run(str(_FIX / "nodeps.md"))
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    # Everything with no deps lands in wave 1.
    assert len(payload["waves"]) == 1


def test_reconcile_order_is_sorted() -> None:
    """Every wave's reconcile_order == sorted(members)."""
    r = _run(str(_FIX / "diamond.md"))
    payload = json.loads(r.stdout)
    for w in payload["waves"]:
        assert w["reconcile_order"] == sorted(w["members"])
