"""Grades every checked-in skill-report fixture (evals/skill-reports/<skill>/
<fixture>/) with skill_report_grader: the fixture's expected.json assertions
over its report.md, and the per-layer count-target rule over the reports of
the three test-architecture skills."""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import skill_report_grader as grader

FIXTURE_ROOT = _REPO_ROOT / "evals" / "skill-reports"
COUNT_TARGET_SKILLS = {"system-test-design", "test-health", "cd-test-architecture"}
FIXTURES = sorted(p.parent for p in FIXTURE_ROOT.glob("*/*/report.md"))


def _id(path) -> str:
    return f"{path.parent.name}/{path.name}"


def test_at_least_one_fixture_is_checked_in() -> None:
    assert FIXTURES, "no skill-report fixtures found; the gates below would pass vacuously"


@pytest.mark.parametrize("fixture", FIXTURES, ids=_id)
def test_fixture_report_meets_its_expected_assertions(fixture) -> None:
    expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    report = (fixture / "report.md").read_text(encoding="utf-8")
    assert grader.grade_report(report, expected) == []


@pytest.mark.parametrize(
    "fixture",
    [f for f in FIXTURES if f.parent.name in COUNT_TARGET_SKILLS],
    ids=_id,
)
def test_fixture_report_has_no_per_layer_count_targets(fixture) -> None:
    report = (fixture / "report.md").read_text(encoding="utf-8")
    assert grader.check_count_targets(report) == []
