"""run-full-eval-parallel.sh — guards the DETERMINISTIC reconciliation the
parallel harness performs. Since #230/#231 the reconcile is a single
`eval_variance --trials-root` pass over each agent's k trials (the unit rules
live in test_eval_validation.py); this file asserts the end-to-end harness
command produces all three trust-rated artifacts from a synthetic per-agent
pool, and that scoping protects un-run agents. Model-free, so it runs in CI.

Ported from tests/repo/run_full_eval_parallel_tests.bats (issue #672).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIANCE = REPO_ROOT / "scripts" / "eval_variance.py"


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "pool" / "agent-a").mkdir(parents=True)
    (tmp_path / "pool" / "agent-b").mkdir(parents=True)
    (tmp_path / "expected" / "clean.json").write_text(
        '{"fixture":"clean.ts","applicableAgents":["agent-a"],'
        '"agents":{"agent-a":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}\n'
    )
    (tmp_path / "expected" / "other.json").write_text(
        '{"fixture":"other.ts","applicableAgents":["agent-b"],'
        '"agents":{"agent-b":{"expectedStatus":"pass","issueCount":{"min":0,"max":0}}}}\n'
    )
    # agent-a: 3/3 pass on clean; agent-b: 3/3 fail on other (was passing).
    for n in (1, 2, 3):
        (tmp_path / "pool" / "agent-a" / f"trial-{n}.json").write_text(
            '{"clean":{"agents":{"agent-a":{"status":"pass","issues":[]}}}}\n'
        )
        (tmp_path / "pool" / "agent-b" / f"trial-{n}.json").write_text(
            '{"other":{"agents":{"agent-b":{"status":"fail","issues":[]}}}}\n'
        )
    (tmp_path / "baseline.json").write_text('{"passing":["other::agent-b"]}')
    return tmp_path


def _reconcile(case: Path, only: str) -> subprocess.CompletedProcess:
    """The exact reconcile command the harness runs."""
    return subprocess.run(
        [
            sys.executable,
            str(VARIANCE),
            "--trials-root",
            str(case / "pool"),
            "--only",
            only,
            "--expected-dir",
            str(case / "expected"),
            "--write-baseline",
            str(case / "baseline.json"),
            "-o",
            str(case / "variance-report.json"),
            "--quarantine-out",
            str(case / "quarantine.json"),
        ],
        capture_output=True,
        text=True,
    )


def test_reconcile_writes_all_three_trust_rated_artifacts(case: Path) -> None:
    res = _reconcile(case, "agent-a,agent-b")
    assert res.returncode == 0, res.stdout + res.stderr
    assert (case / "baseline.json").is_file()
    assert (case / "variance-report.json").is_file()
    assert (case / "quarantine.json").is_file()
    report = json.loads((case / "variance-report.json").read_text())
    assert report["schema"] == "eval-variance/v1"


def test_reconcile_adds_a_solidly_passing_agent_and_removes_a_consistently_failing_one(
    case: Path,
) -> None:
    _reconcile(case, "agent-a,agent-b")
    baseline = json.loads((case / "baseline.json").read_text())
    # agent-a added; other::agent-b removed (0/3)
    assert sorted(baseline["passing"]) == ["clean::agent-a"]


def test_an_un_run_agents_baseline_pairs_survive_the_reconcile(case: Path) -> None:
    # Only agent-a runs; agent-b's prior pair must be left untouched.
    _reconcile(case, "agent-a")
    baseline = json.loads((case / "baseline.json").read_text())
    assert sorted(baseline["passing"]) == ["clean::agent-a", "other::agent-b"]
