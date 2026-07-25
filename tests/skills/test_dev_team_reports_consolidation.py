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

CODE_REVIEW_SKILL = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")

CODE_REVIEW_OUTPUT_FORMAT = (
    PLUGIN_ROOT / "skills" / "code-review" / "output-format.md"
).read_text(encoding="utf-8")

TRIAGE_SKILL = (
    PLUGIN_ROOT / "skills" / "triage" / "SKILL.md"
).read_text(encoding="utf-8")

LEDGER_PY = (
    PLUGIN_ROOT / "skills" / "code-review" / "scripts" / "ledger.py"
).read_text(encoding="utf-8")

CONSOLIDATE_PY = (
    PLUGIN_ROOT / "skills" / "code-review" / "scripts" / "consolidate.py"
).read_text(encoding="utf-8")

SLICED_MODE = (
    PLUGIN_ROOT / "skills" / "code-review" / "sliced-mode.md"
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


def test_code_review_skill_and_output_format_write_to_consolidated_location():
    assert "DEV_TEAM_REPORTS" not in CODE_REVIEW_SKILL, (
        "code-review/SKILL.md must not reference the legacy bare "
        "DEV_TEAM_REPORTS/ path"
    )
    assert ".dev-team-reports/code-review.md" in CODE_REVIEW_SKILL, (
        "code-review/SKILL.md step 7 must target "
        ".dev-team-reports/code-review.md"
    )
    assert "DEV_TEAM_REPORTS" not in CODE_REVIEW_OUTPUT_FORMAT, (
        "code-review/output-format.md must not reference the legacy bare "
        "DEV_TEAM_REPORTS/ path"
    )
    assert ".dev-team-reports/code-review" in CODE_REVIEW_OUTPUT_FORMAT, (
        "code-review/output-format.md must describe the sliced-mode ledger "
        "under .dev-team-reports/code-review/"
    )


def test_triage_skill_writes_to_consolidated_location_with_collision_suffix_intact():
    assert "DEV_TEAM_REPORTS" not in TRIAGE_SKILL, (
        "triage/SKILL.md must not reference the legacy bare DEV_TEAM_REPORTS/ "
        "path"
    )
    assert ".dev-team-reports/triage/<slug>.md" in TRIAGE_SKILL, (
        "triage/SKILL.md must target .dev-team-reports/triage/<slug>.md"
    )
    assert "-2`, `-3`, … up to `-99`" in TRIAGE_SKILL, (
        "triage/SKILL.md's collision-suffix behavior must remain unchanged "
        "in substance"
    )


def test_ledger_and_consolidate_scripts_target_consolidated_root():
    assert "DEV_TEAM_REPORTS" not in LEDGER_PY, (
        "ledger.py must not reference the legacy bare DEV_TEAM_REPORTS/ "
        "path literal"
    )
    assert '".dev-team-reports"' in LEDGER_PY, (
        "ledger.py's _cr_dir() must resolve under .dev-team-reports/"
    )
    assert "DEV_TEAM_REPORTS" not in CONSOLIDATE_PY, (
        "consolidate.py must not reference the legacy bare DEV_TEAM_REPORTS/ "
        "path literal"
    )
    assert '".dev-team-reports"' in CONSOLIDATE_PY, (
        "consolidate.py's raw_dir resolution must target .dev-team-reports/"
    )


def test_sliced_mode_doc_describes_consolidated_root():
    assert "DEV_TEAM_REPORTS" not in SLICED_MODE, (
        "sliced-mode.md must not reference the legacy bare DEV_TEAM_REPORTS/ "
        "path"
    )
    assert ".dev-team-reports/code-review" in SLICED_MODE, (
        "sliced-mode.md must describe the ledger/section artifacts under "
        ".dev-team-reports/code-review/"
    )
