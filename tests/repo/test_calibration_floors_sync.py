"""Calibration-floors completeness sensor. knowledge/calibration-floors.json
must stay in sync with (a) the fixture-bearing agents/skills declared across
evals/expected/*.json and (b) the agents/ and skills/ directories on disk.
Guards the policy artifact introduced by issue #880 (slice 1 of epic #879):
without this test a new eval fixture could reference an agent with no
calibration floor, or a hand-edited floor entry could drift into an invalid
riskClass/value or point at a target that no longer exists.

Structural template: tests/repo/test_registry_sync.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "check_calibration_floors_sync.py"

_BASELINE_FLOORS = {
    "foo": {"riskClass": "standard", "floor": 0.9},
    "bar": {"riskClass": "advisory", "floor": 0.8},
}


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    """A minimal synthetic tree: one agent (foo), one skill (bar), one eval
    fixture referencing both, and a floors table covering both."""
    (tmp_path / "plugins" / "dev-team" / "agents").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "skills" / "bar").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "knowledge").mkdir(parents=True)
    (tmp_path / "evals" / "expected").mkdir(parents=True)

    (tmp_path / "plugins" / "dev-team" / "agents" / "foo.md").write_text(
        "---\nname: foo\neffort: medium\n---\n"
    )
    (tmp_path / "plugins" / "dev-team" / "skills" / "bar" / "SKILL.md").write_text(
        "---\nname: bar\n---\n"
    )
    (tmp_path / "evals" / "expected" / "sample.json").write_text(
        json.dumps(
            {
                "fixture": "sample",
                "applicableAgents": ["foo"],
                "applicableSkills": ["bar"],
            }
        )
    )
    _write_floors(tmp_path, _BASELINE_FLOORS)
    return tmp_path


def _write_floors(root: Path, floors: dict) -> None:
    (root / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json").write_text(
        json.dumps(floors)
    )


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_check_passes_on_the_real_repository_tree() -> None:
    res = _run(REPO_ROOT)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_fully_registered_fixture_is_in_sync(fixture_root: Path) -> None:
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_fixture_bearing_agent_with_no_floor_entry_fails_missing(
    fixture_root: Path,
) -> None:
    (fixture_root / "plugins" / "dev-team" / "agents" / "baz.md").write_text(
        "---\nname: baz\neffort: low\n---\n"
    )
    (fixture_root / "evals" / "expected" / "sample2.json").write_text(
        json.dumps({"fixture": "sample2", "applicableAgents": ["baz"]})
    )
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "MISSING" in out
    assert "baz" in out


def test_an_orphan_floor_entry_fails_orphan(fixture_root: Path) -> None:
    floors = dict(_BASELINE_FLOORS)
    floors["ghost"] = {"riskClass": "standard", "floor": 0.9}
    _write_floors(fixture_root, floors)
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "ORPHAN" in out
    assert "ghost" in out


def test_an_out_of_range_floor_fails_invalid(fixture_root: Path) -> None:
    floors = dict(_BASELINE_FLOORS)
    floors["foo"] = {"riskClass": "standard", "floor": 1.5}
    _write_floors(fixture_root, floors)
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "INVALID" in out
    assert "foo" in out


def test_an_unknown_risk_class_fails_invalid(fixture_root: Path) -> None:
    floors = dict(_BASELINE_FLOORS)
    floors["bar"] = {"riskClass": "critical", "floor": 0.8}
    _write_floors(fixture_root, floors)
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "INVALID" in out
    assert "bar" in out


def test_a_stale_fixture_reference_to_a_removed_agent_is_not_required(
    fixture_root: Path,
) -> None:
    # A fixture may still reference an agent that was intentionally removed
    # from disk (e.g. test-modernization-review, retired by issue #536). That
    # name is not "fixture-bearing" in the live sense -- it must not be
    # reported MISSING, since the agent it would calibrate no longer exists.
    (fixture_root / "evals" / "expected" / "sample3.json").write_text(
        json.dumps({"fixture": "sample3", "applicableAgents": ["long-gone-agent"]})
    )
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_metadata_comment_key_is_ignored(fixture_root: Path) -> None:
    floors = dict(_BASELINE_FLOORS)
    floors["_comment"] = "not a target, just documentation"
    _write_floors(fixture_root, floors)
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr
