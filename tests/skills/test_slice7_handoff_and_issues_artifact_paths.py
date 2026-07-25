"""Content-guard: handoff, harness-e2e-check, headless-run,
human-oversight-protocol, issues-from-assessment, and issues-from-plan no
longer describe bare project-scoped memory/plans writer targets (Slice 7,
plan opt-in-metrics-and-claude-scoped-artifacts.md).

harness-e2e-check/SKILL.md's `<scratch>/lesson-fixture/metrics/...` and
`<scratch>/toy-repo/plans/calc-ops.md` paths are deliberately excluded — they
are literal outputs of make_lesson_fixtures.py's own hardcoded scratch-fixture
layout (test data, not a real project artifact-resolution path) and the
/plan-domain toy-repo fixture file, respectively.

`plans/` references describing the operator-facing implementation-plan-file
convention (issues-from-plan/SKILL.md's fallback search, human-oversight-
protocol's evidence_shown examples) are deliberately left bare — the same
distinct concept as /plan's own shipped default.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

HANDOFF = (PLUGIN_ROOT / "skills" / "handoff" / "SKILL.md").read_text(
    encoding="utf-8"
)
SUMMARY_TEMPLATES = (
    PLUGIN_ROOT / "skills" / "handoff" / "references" / "summary-templates.md"
).read_text(encoding="utf-8")
HARNESS_E2E = (PLUGIN_ROOT / "skills" / "harness-e2e-check" / "SKILL.md").read_text(
    encoding="utf-8"
)
HEADLESS_RUN = (PLUGIN_ROOT / "skills" / "headless-run" / "SKILL.md").read_text(
    encoding="utf-8"
)
HUMAN_OVERSIGHT = (
    PLUGIN_ROOT / "skills" / "human-oversight-protocol" / "SKILL.md"
).read_text(encoding="utf-8")
ISSUES_FROM_PLAN = (
    PLUGIN_ROOT / "skills" / "issues-from-plan" / "SKILL.md"
).read_text(encoding="utf-8")

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")


def test_handoff_skill_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(HANDOFF)
    assert ".claude/memory/{date}-{task-slug}.md" in HANDOFF


def test_summary_templates_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(SUMMARY_TEMPLATES)


def test_harness_e2e_check_boundary_events_relocated_fixture_paths_untouched() -> None:
    assert ".claude/metrics/boundary-events.jsonl" in HARNESS_E2E
    # the scratch-fixture generator's own hardcoded bare layout is untouched
    assert "<scratch>/lesson-fixture/metrics/config-changelog.jsonl" in HARNESS_E2E
    assert "<scratch>/lesson-fixture/memory/lesson-validation.json" in HARNESS_E2E


def test_headless_run_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(HEADLESS_RUN)


def test_human_oversight_protocol_memory_examples_relocated() -> None:
    assert "write it to `.claude/memory/` first" in HUMAN_OVERSIGHT
    assert '".claude/memory/build-issue-867.md"' in HUMAN_OVERSIGHT
    # the /plan-domain example path stays bare
    assert '"plans/issue-867-gate-decision-audit.md"' in HUMAN_OVERSIGHT


def test_issues_from_plan_memory_search_location_relocated_plans_stays_bare() -> None:
    assert "`.claude/memory/` directory (phase progress files)" in ISSUES_FROM_PLAN
    assert "`plans/` directory" in ISSUES_FROM_PLAN
