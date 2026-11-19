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

import coverage_evidence_detect as detector
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
    assert grader.validate_expected(expected) is None
    unknown = set(expected) - set(grader._ASSERTION_KEYS)
    assert not unknown, f"unknown assertion keys (typo?): {sorted(unknown)}"
    assert expected.get("regex_present") or expected.get("sections_present")
    assert grader.grade_report(report, expected) == []


@pytest.mark.parametrize(
    "fixture",
    [f for f in FIXTURES if f.parent.name in COUNT_TARGET_SKILLS],
    ids=_id,
)
def test_fixture_report_has_no_per_layer_count_targets(fixture) -> None:
    report = (fixture / "report.md").read_text(encoding="utf-8")
    assert grader.check_count_targets(report) == []


# One fixture per behavior the system-test-design skill promises; a missing
# directory means a promised behavior has no golden report.
REQUIRED_SYSTEM_TEST_DESIGN_FIXTURES = {
    "three-repos", "discovered-repo", "unindexed-repo", "no-repowise", "e2e-only",
    "overlap-only", "shared-table", "e2e-triage-delete-pushdown", "async-handoff-keep",
    "aliased-journeys", "gap-list", "overlap-coverage-coveragepy", "overlap-coverage-cobertura",
    "overlap-coverage-istanbul", "overlap-mutation-stryker", "overlap-mutation-mutmut",
    "overlap-mutation-wins", "overlap-coverage-disagrees", "overlap-static-missing",
    "overlap-static-unrecognised", "overlap-static-malformed", "overlap-static-no-contexts",
    "overlap-partial-evidence", "overlap-cap", "overlap-single-layer",
}


def test_every_required_system_test_design_fixture_exists() -> None:
    present = {f.name for f in FIXTURES if f.parent.name == "system-test-design"}
    assert REQUIRED_SYSTEM_TEST_DESIGN_FIXTURES <= present


def test_test_health_multi_repo_fixture_exists() -> None:
    assert any(f.parent.name == "test-health" and f.name == "multi-repo" for f in FIXTURES)


EVIDENCE_FIXTURES = sorted(p.parent for p in FIXTURE_ROOT.glob("*/*/evidence.json"))


def test_every_overlap_evidence_fixture_declares_its_evidence() -> None:
    names = {f.name for f in EVIDENCE_FIXTURES}
    expected = {n for n in REQUIRED_SYSTEM_TEST_DESIGN_FIXTURES
                if n.startswith(("overlap-coverage-", "overlap-mutation-", "overlap-static-"))
                or n == "overlap-partial-evidence"}
    assert expected - {"overlap-static-missing"} <= names


@pytest.mark.parametrize("fixture", EVIDENCE_FIXTURES, ids=_id)
def test_fixture_evidence_is_classified_as_declared(fixture) -> None:
    for entry in json.loads((fixture / "evidence.json").read_text(encoding="utf-8")):
        path = fixture / "repos" / entry["repo"] / entry["path"]
        got = detector.classify(entry["kind"], str(path))
        assert got["format"] == entry["format"]
        if entry["reason"] is None:
            assert got["reason"] is None
        else:
            assert got["reason"].startswith(entry["reason"])
