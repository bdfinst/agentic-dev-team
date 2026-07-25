"""Slice 9 — `DEV_TEAM_REPORTS/` and `reports/` consolidate into
`.dev-team-reports/` (plans/opt-in-metrics-and-claude-scoped-artifacts.md,
Slice 9). Content-guard tests, one function per step, asserting the legacy
bare `DEV_TEAM_REPORTS/` fragment is gone from each step's file set and the
new `.dev-team-reports/` location is documented in its place.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

REPORT_OUTPUT_LOCATION = (
    PLUGIN_ROOT / "knowledge" / "report-output-location.md"
).read_text(encoding="utf-8")

REVIEW_AGENT_SKILL = (
    PLUGIN_ROOT / "skills" / "review-agent" / "SKILL.md"
).read_text(encoding="utf-8")


def test_report_output_location_has_no_legacy_dev_team_reports_references():
    assert "DEV_TEAM_REPORTS" not in REPORT_OUTPUT_LOCATION, (
        "report-output-location.md must not reference the legacy bare "
        "DEV_TEAM_REPORTS/ path — it should describe the consolidated "
        ".dev-team-reports/ location only"
    )
    assert ".dev-team-reports/" in REPORT_OUTPUT_LOCATION, (
        "report-output-location.md must document the consolidated "
        ".dev-team-reports/ location"
    )


def test_review_agent_skill_writes_to_consolidated_location():
    assert "DEV_TEAM_REPORTS" not in REVIEW_AGENT_SKILL, (
        "review-agent/SKILL.md must not reference the legacy bare "
        "DEV_TEAM_REPORTS/ path"
    )
    assert ".dev-team-reports/<agent-name>.md" in REVIEW_AGENT_SKILL, (
        "review-agent/SKILL.md step 4b must target "
        ".dev-team-reports/<agent-name>.md"
    )
