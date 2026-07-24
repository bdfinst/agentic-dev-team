"""#110 — persona on/off: per-agent pass@k delta, only "real" when it clears the
variance band (neither run flapped). Model-free core (synthetic on/off trials).

Ported from tests/repo/eval_persona_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

PERSONA = REPO_ROOT / "scripts" / "eval_persona.py"

ISSUES = [{"severity": "warning", "message": "x"}]


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()
    (tmp_path / "expected" / "f1.json").write_text(
        json.dumps(
            {
                "fixture": "f1.ts",
                "applicableAgents": ["a"],
                "agents": {
                    "a": {"expectedStatus": "fail", "issueCount": {"min": 1, "max": 3}}
                },
            }
        )
    )
    (tmp_path / "expected" / "f2.json").write_text(
        json.dumps(
            {
                "fixture": "f2.ts",
                "applicableAgents": ["a"],
                "agents": {
                    "a": {"expectedStatus": "fail", "issueCount": {"min": 1, "max": 3}}
                },
            }
        )
    )
    return tmp_path


def _trial(f1_status: str, f2_status: str) -> str:
    f1_issues = ISSUES if f1_status == "fail" else []
    f2_issues = ISSUES if f2_status == "fail" else []
    return json.dumps(
        {
            "f1": {"agents": {"a": {"status": f1_status, "issues": f1_issues}}},
            "f2": {"agents": {"a": {"status": f2_status, "issues": f2_issues}}},
        }
    )


def _run(case: Path) -> dict:
    res = subprocess.run(
        [
            sys.executable,
            str(PERSONA),
            "--on-trials",
            str(case / "on"),
            "--off-trials",
            str(case / "off"),
            "--expected-dir",
            str(case / "expected"),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout)


def test_persona_a_real_non_flapping_delta_is_reported_as_added_value(
    case: Path,
) -> None:
    # ON: both fixtures pass (fail status w/ 1 issue) in both trials -> mean 1.0
    for n in (1, 2):
        (case / "on" / f"t{n}.json").write_text(_trial("fail", "fail"))
    # OFF: f1 passes, f2 always wrong status (pass) -> stable fail -> mean 0.5, no flap
    for n in (1, 2):
        (case / "off" / f"t{n}.json").write_text(_trial("fail", "pass"))

    data = _run(case)
    assert data["by_agent"]["a"]["delta"] == 0.5
    assert data["by_agent"]["a"]["real"] is True
    assert data["persona_helps"] == 1


def test_persona_identical_on_off_is_an_honest_null_no_effect(case: Path) -> None:
    for d in ("on", "off"):
        for n in (1, 2):
            (case / d / f"t{n}.json").write_text(_trial("fail", "fail"))

    data = _run(case)
    assert data["by_agent"]["a"]["delta"] == 0.0
    assert data["by_agent"]["a"]["real"] is False
    assert "no effect" in data["by_agent"]["a"]["verdict"]


def test_persona_a_flapping_run_marks_the_delta_as_within_noise_not_real_110(
    case: Path,
) -> None:
    for n in (1, 2):
        (case / "on" / f"t{n}.json").write_text(_trial("fail", "fail"))
    # OFF flaps on f2 (pass then fail) -> flaky -> delta is within noise band
    (case / "off" / "t1.json").write_text(_trial("fail", "fail"))
    (case / "off" / "t2.json").write_text(_trial("fail", "pass"))

    data = _run(case)
    assert data["by_agent"]["a"]["flapped"] is True
    assert data["by_agent"]["a"]["real"] is False
    assert "noise" in data["by_agent"]["a"]["verdict"]
