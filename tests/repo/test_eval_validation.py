"""Eval validation gap — Phase 1 (#229/#230/#231). Trust-gated baseline writes
and quarantine consumption. Model-free (synthetic per-trial actuals), so it
runs in CI like the rest of the grader.

Ported from tests/repo/eval_validation_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIANCE = REPO_ROOT / "scripts" / "eval_variance.py"
GRADE = REPO_ROOT / "scripts" / "eval_grade.py"

STEMS = ("a", "b", "c", "d")


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "trials").mkdir()
    # One single-agent fixture per agent so pairs are <stem>::<agent>.
    for stem in STEMS:
        (tmp_path / "expected" / f"{stem}.json").write_text(
            json.dumps(
                {
                    "fixture": f"{stem}.ts",
                    "applicableAgents": [f"ag-{stem}"],
                    "agents": {
                        f"ag-{stem}": {
                            "expectedStatus": "pass",
                            "issueCount": {"min": 0, "max": 0},
                        }
                    },
                }
            )
        )
        (tmp_path / "trials" / f"ag-{stem}").mkdir()
    return tmp_path


def _write_trials(case: Path, stem: str, *statuses: str) -> None:
    """Write N trials for agent ag-<stem> on fixture <stem> with the given
    status each."""
    for n, status in enumerate(statuses, start=1):
        (case / "trials" / f"ag-{stem}" / f"trial-{n}.json").write_text(
            json.dumps(
                {stem: {"agents": {f"ag-{stem}": {"status": status, "issues": []}}}}
            )
        )


def _run_baseline(case: Path, only: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(VARIANCE),
            "--trials-root",
            str(case / "trials"),
            "--only",
            only,
            "--expected-dir",
            str(case / "expected"),
            "--write-baseline",
            str(case / "baseline.json"),
            "--quarantine-out",
            str(case / "quarantine.json"),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_all_pass_pair_is_added_to_the_baseline(case: Path) -> None:
    _write_trials(case, "a", "pass", "pass", "pass")
    (case / "baseline.json").write_text('{"passing":[]}')
    res = _run_baseline(case, "ag-a")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    assert data["passing"] == ["a::ag-a"]


def test_consistently_failing_pair_pass_at_k_0_over_min_trials_is_removed(
    case: Path,
) -> None:
    _write_trials(case, "b", "fail", "fail", "fail")
    (case / "baseline.json").write_text('{"passing":["b::ag-b"]}')
    res = _run_baseline(case, "ag-b")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    assert data["passing"] == []


def test_single_trial_failure_does_not_delete_trials_less_than_min_trials_9_fix(
    case: Path,
) -> None:
    _write_trials(case, "b", "fail")  # exactly one trial
    (case / "baseline.json").write_text('{"passing":["b::ag-b"]}')
    res = _run_baseline(case, "ag-b")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    assert data["passing"] == ["b::ag-b"]  # survived the noisy single sample


def test_flaky_pair_is_quarantined_and_not_removed(case: Path) -> None:
    _write_trials(case, "c", "pass", "pass", "fail")  # 2/3 -> flaky
    (case / "baseline.json").write_text('{"passing":["c::ag-c"]}')
    res = _run_baseline(case, "ag-c")
    assert res.returncode == 0, res.stdout + res.stderr
    baseline = json.loads((case / "baseline.json").read_text())
    assert baseline["passing"] == ["c::ag-c"]  # kept
    quarantine = json.loads((case / "quarantine.json").read_text())
    assert quarantine["quarantine"] == ["c::ag-c"]  # and quarantined


def test_per_agent_scoping_leaves_an_un_run_agents_baseline_pairs_untouched(
    case: Path,
) -> None:
    _write_trials(case, "a", "pass", "pass", "pass")  # only ag-a runs
    (case / "baseline.json").write_text('{"passing":["d::ag-d"]}')
    res = _run_baseline(case, "ag-a")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    assert sorted(data["passing"]) == ["a::ag-a", "d::ag-d"]  # d untouched, a added


def test_grader_excludes_quarantined_pairs_from_blocking_231(case: Path) -> None:
    # c is flaky+quarantined and in the baseline; a fresh run where it fails
    # again must NOT block the gate.
    (case / "baseline.json").write_text('{"passing":["c::ag-c"]}')
    (case / "quarantine.json").write_text('{"quarantine":["c::ag-c"]}')
    (case / "run.json").write_text(
        json.dumps({"c": {"agents": {"ag-c": {"status": "fail", "issues": []}}}})
    )
    res = subprocess.run(
        [
            sys.executable,
            str(GRADE),
            "--expected-dir",
            str(case / "expected"),
            "--actuals",
            str(case / "run.json"),
            "--baseline",
            str(case / "baseline.json"),
            "--quarantine",
            str(case / "quarantine.json"),
            "--only",
            "ag-c",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_harvest_id_is_stamped_into_every_written_artifact_232_provenance(
    case: Path,
) -> None:
    _write_trials(case, "a", "pass", "pass", "pass")
    (case / "baseline.json").write_text('{"passing":[]}')
    res = subprocess.run(
        [
            sys.executable,
            str(VARIANCE),
            "--trials-root",
            str(case / "trials"),
            "--only",
            "ag-a",
            "--expected-dir",
            str(case / "expected"),
            "--harvest-id",
            "H-123",
            "--write-baseline",
            str(case / "baseline.json"),
            "-o",
            str(case / "variance.json"),
            "--quarantine-out",
            str(case / "quarantine.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    baseline = json.loads((case / "baseline.json").read_text())
    variance = json.loads((case / "variance.json").read_text())
    quarantine = json.loads((case / "quarantine.json").read_text())
    assert baseline["harvest_id"] == "H-123"
    assert variance["harvest_id"] == "H-123"
    assert quarantine["harvest_id"] == "H-123"


def test_grader_still_blocks_a_real_non_quarantined_regression(case: Path) -> None:
    (case / "baseline.json").write_text('{"passing":["c::ag-c"]}')
    (case / "quarantine.json").write_text('{"quarantine":[]}')
    (case / "run.json").write_text(
        json.dumps({"c": {"agents": {"ag-c": {"status": "fail", "issues": []}}}})
    )
    res = subprocess.run(
        [
            sys.executable,
            str(GRADE),
            "--expected-dir",
            str(case / "expected"),
            "--actuals",
            str(case / "run.json"),
            "--baseline",
            str(case / "baseline.json"),
            "--quarantine",
            str(case / "quarantine.json"),
            "--only",
            "ag-c",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
