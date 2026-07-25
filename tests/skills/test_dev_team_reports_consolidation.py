"""Slice 9 — `DEV_TEAM_REPORTS/` and `reports/` consolidate into
`.dev-team-reports/` (plans/opt-in-metrics-and-claude-scoped-artifacts.md,
Slice 9). Content-guard tests, one function per step, asserting the legacy
bare `DEV_TEAM_REPORTS/` fragment is gone from each step's file set and the
new `.dev-team-reports/` location is documented in its place.
"""

from __future__ import annotations

import re

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

# Step 9.6 sweep: every remaining reference-only consumer identified in the
# plan's Slice 9 file list, excluding CHANGELOG.md / metrics/config-changelog.jsonl
# (historical, append-only) and knowledge/index.json (build artifact, regenerates).
STEP_9_6_SWEEP_FILES = [
    PLUGIN_ROOT / "skills" / "ship" / "SKILL.md",
    PLUGIN_ROOT / "skills" / "exploratory-testing" / "SKILL.md",
    PLUGIN_ROOT / "skills" / "report-pdf" / "SKILL.md",
    PLUGIN_ROOT / "skills" / "project-init" / "references" / "configs.md",
    PLUGIN_ROOT / "knowledge" / "skills-registry.md",
    PLUGIN_ROOT / "knowledge" / "report-pdf-integration.md",
    PLUGIN_ROOT / "knowledge" / "report-print.css",
    PLUGIN_ROOT / "knowledge" / "report-to-pdf.md",
    PLUGIN_ROOT / "knowledge" / "request-processing-flow.md",
    PLUGIN_ROOT / "docs" / "triage-workflow.md",
    PLUGIN_ROOT / "docs" / "workflows.md",
    PLUGIN_ROOT / "docs" / "skills.md",
]


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


def test_step_9_6_sweep_files_have_no_legacy_dev_team_reports_references():
    for path in STEP_9_6_SWEEP_FILES:
        text = path.read_text(encoding="utf-8")
        assert "DEV_TEAM_REPORTS" not in text, (
            f"{path} must not reference the legacy bare DEV_TEAM_REPORTS/ path"
        )


def test_js_scaffold_gitignore_template_emits_consolidated_location():
    configs = (
        PLUGIN_ROOT / "skills" / "project-init" / "references" / "configs.md"
    ).read_text(encoding="utf-8")
    assert ".dev-team-reports/" in configs, (
        "the JS-scaffold .gitignore template must emit .dev-team-reports/ "
        "for new downstream projects"
    )


def test_js_scaffold_gitignore_template_tracks_test_improve_report_data():
    """#1412: a blanket `.dev-team-reports/` ignore in the JS-scaffold
    template would silently defeat /test-improve's git-tracked <slug>/data/
    sibling directory for every newly-provisioned project. The template must
    use the same anchored deny-all + tracked-exception shape as this repo's
    own .gitignore (test_dev_team_reports_gitignore_consolidation.py)."""
    configs = (
        PLUGIN_ROOT / "skills" / "project-init" / "references" / "configs.md"
    ).read_text(encoding="utf-8")
    # Scope to the emitted .gitignore fence itself — a match against the
    # whole file would also pass if these literals only ever appeared in
    # surrounding prose, never in the block actually shipped downstream.
    fence = re.search(r"## \.gitignore\n\n```\n(.*?)\n```", configs, re.DOTALL)
    assert fence, "no fenced .gitignore block found under '## .gitignore' in configs.md"
    block = fence.group(1)
    assert "/.dev-team-reports/*" in block, (
        "the JS-scaffold .gitignore template must anchor the deny-all rule "
        "as /.dev-team-reports/*, not a blanket .dev-team-reports/ ignore"
    )
    assert "!/.dev-team-reports/test-improve/" in block, (
        "the JS-scaffold .gitignore template must re-include "
        "/.dev-team-reports/test-improve/ so /test-improve's report data/ "
        "sibling directory is git-tracked in newly-provisioned projects"
    )
    # The re-include must stay directory-level — git never re-includes a
    # path whose parent directory is itself excluded by the deny-all above,
    # so a narrower e.g. `!/.dev-team-reports/test-improve/*/data/` would
    # silently match nothing.
    assert "!/.dev-team-reports/test-improve/*/data/" not in block
