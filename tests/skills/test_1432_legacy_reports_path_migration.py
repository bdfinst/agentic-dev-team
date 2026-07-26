"""#1432 — nine report-producing skills migrate off the legacy bare
`reports/` path onto the consolidated `.dev-team-reports/` location (the
same location #1415/Slice 9 already moved `/review-agent`, `/code-review`,
and `/triage` to — see `test_dev_team_reports_consolidation.py`). Content-
guard tests, one function per migrated skill, asserting the new location is
documented and the legacy bare fragment is gone.

`issues-from-assessment/SKILL.md` carries one dependent reference to
`cd-test-architecture`'s output path (also migrated here) plus one
pre-existing, unrelated dangling reference to a `reports/legacy-test-
modernization-prompt.md` file that predates #1432 and does not exist in the
repo — deliberately excluded from the bare-fragment assertion below so this
module doesn't fail on a defect outside its own scope.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

_BARE_REPORTS_RE = re.compile(r"(?<!\.dev-team-)reports/")

CD_TEST_ARCHITECTURE = (
    PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"
).read_text(encoding="utf-8")
TEST_HEALTH = (PLUGIN_ROOT / "skills" / "test-health" / "SKILL.md").read_text(
    encoding="utf-8"
)
HARNESS_AUDIT = (PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md").read_text(
    encoding="utf-8"
)
ORCHESTRATION_BENCHMARK = (
    PLUGIN_ROOT / "skills" / "orchestration-benchmark" / "SKILL.md"
).read_text(encoding="utf-8")
FRONTEND_ARCHITECTURE = (
    PLUGIN_ROOT / "skills" / "frontend-architecture" / "SKILL.md"
).read_text(encoding="utf-8")
COMPETITIVE_ANALYSIS = (
    PLUGIN_ROOT / "skills" / "competitive-analysis" / "SKILL.md"
).read_text(encoding="utf-8")
HARNESS_E2E_CHECK = (
    PLUGIN_ROOT / "skills" / "harness-e2e-check" / "SKILL.md"
).read_text(encoding="utf-8")
TEST_DESIGN = (PLUGIN_ROOT / "skills" / "test-design" / "SKILL.md").read_text(
    encoding="utf-8"
)
TEST_DESIGN_ADVISOR = (
    PLUGIN_ROOT / "skills" / "test-design-advisor" / "SKILL.md"
).read_text(encoding="utf-8")
ISSUES_FROM_ASSESSMENT = (
    PLUGIN_ROOT / "skills" / "issues-from-assessment" / "SKILL.md"
).read_text(encoding="utf-8")
REPORT_PDF_INTEGRATION = (
    PLUGIN_ROOT / "knowledge" / "report-pdf-integration.md"
).read_text(encoding="utf-8")
REPORT_PDF_SKILL = (PLUGIN_ROOT / "skills" / "report-pdf" / "SKILL.md").read_text(
    encoding="utf-8"
)


def test_cd_test_architecture_report_path_relocated() -> None:
    assert ".dev-team-reports/cd-test-architecture-<app>.md" in CD_TEST_ARCHITECTURE
    assert not _BARE_REPORTS_RE.search(CD_TEST_ARCHITECTURE)


def test_test_health_report_path_relocated() -> None:
    assert ".dev-team-reports/test-health-<date>.md" in TEST_HEALTH
    assert not _BARE_REPORTS_RE.search(TEST_HEALTH)


def test_harness_audit_report_path_relocated() -> None:
    assert ".dev-team-reports/harness-audit-<date>.md" in HARNESS_AUDIT
    assert not _BARE_REPORTS_RE.search(HARNESS_AUDIT)


def test_orchestration_benchmark_report_path_relocated() -> None:
    assert ".dev-team-reports/orchestration-benchmark-<date>.md" in ORCHESTRATION_BENCHMARK
    assert not _BARE_REPORTS_RE.search(ORCHESTRATION_BENCHMARK)


def test_frontend_architecture_report_path_relocated() -> None:
    assert ".dev-team-reports/frontend-architecture-<date>.md" in FRONTEND_ARCHITECTURE
    assert not _BARE_REPORTS_RE.search(FRONTEND_ARCHITECTURE)


def test_competitive_analysis_report_path_relocated() -> None:
    assert ".dev-team-reports/competitive-analysis-<date>.md" in COMPETITIVE_ANALYSIS
    assert not _BARE_REPORTS_RE.search(COMPETITIVE_ANALYSIS)


def test_harness_e2e_check_report_path_relocated() -> None:
    assert ".dev-team-reports/harness-e2e-check-<date>.md" in HARNESS_E2E_CHECK
    assert not _BARE_REPORTS_RE.search(HARNESS_E2E_CHECK)


def test_test_design_report_path_relocated() -> None:
    assert ".dev-team-reports/test-design-<date>.md" in TEST_DESIGN
    assert not _BARE_REPORTS_RE.search(TEST_DESIGN)


def test_test_design_advisor_report_path_relocated() -> None:
    assert ".dev-team-reports/test-design-<target>.md" in TEST_DESIGN_ADVISOR
    assert not _BARE_REPORTS_RE.search(TEST_DESIGN_ADVISOR)


def test_issues_from_assessment_dependent_reference_relocated() -> None:
    # Scoped literal check, not the blanket _BARE_REPORTS_RE sweep: this file
    # also carries a pre-existing, unrelated dangling reference to
    # `reports/legacy-test-modernization-prompt.md` (a file that does not
    # exist in the repo, predates #1432, and is out of this issue's scope).
    assert ".dev-team-reports/cd-test-architecture-<app>.md" in ISSUES_FROM_ASSESSMENT


def test_report_pdf_integration_table_relocated() -> None:
    for path_frag in (
        ".dev-team-reports/test-health-<date>.md",
        ".dev-team-reports/cd-test-architecture-<app>.md",
        ".dev-team-reports/harness-audit-<date>.md",
    ):
        assert path_frag in REPORT_PDF_INTEGRATION
    assert "(including the `reports/`" not in REPORT_PDF_INTEGRATION


def test_report_pdf_skill_example_relocated() -> None:
    assert ".dev-team-reports/test-health-2026-07-16.md" in REPORT_PDF_SKILL
