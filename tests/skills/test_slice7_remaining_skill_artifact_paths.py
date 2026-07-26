"""Content-guard: the remaining bare metrics/memory writer-target references
identified by Slice 7's live sweep resolve to their .claude/-nested
equivalents (plan opt-in-metrics-and-claude-scoped-artifacts.md, Slice 7,
Step 7.2).

Covers orchestration-benchmark/SKILL.md, plan/SKILL.md (a second,
previously-missed review-value/config-changelog occurrence — the code-review
fix pass only caught the non-interactive-path sentence), quality-gate-
pipeline/SKILL.md, session-review/SKILL.md (pending-review.jsonl reads only —
its own memory/metrics scratch-state writes stay bare per the plan's Step
5.11 "/session-review is out of scope" declaration), ship/SKILL.md, and
test-audit-disable/SKILL.md.

`.plans/domain/` (ubiquitous-language/SKILL.md), `~/.claude/agent-memory/`
(templates/agents/agent-template.md), and security-assessment's own memory/
patterns (static-analysis-integration/references/security-review-adapter.md)
are deliberately excluded — established false-positive categories.

Note: orchestration-benchmark's own report path (along with 8 other skills)
was migrated off the bare `reports/` path by #1432 — see
`tests/skills/test_1432_legacy_reports_path_migration.py`, not the `.claude/`
metrics/memory migration this module otherwise covers.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

ORCHESTRATION_BENCHMARK = (
    PLUGIN_ROOT / "skills" / "orchestration-benchmark" / "SKILL.md"
).read_text(encoding="utf-8")
PLAN_SKILL = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text(
    encoding="utf-8"
)
QUALITY_GATE = (
    PLUGIN_ROOT / "skills" / "quality-gate-pipeline" / "SKILL.md"
).read_text(encoding="utf-8")
SESSION_REVIEW = (PLUGIN_ROOT / "skills" / "session-review" / "SKILL.md").read_text(
    encoding="utf-8"
)
SHIP_SKILL = (PLUGIN_ROOT / "skills" / "ship" / "SKILL.md").read_text(
    encoding="utf-8"
)
TEST_AUDIT_DISABLE = (
    PLUGIN_ROOT / "skills" / "test-audit-disable" / "SKILL.md"
).read_text(encoding="utf-8")

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")


def test_orchestration_benchmark_review_value_relocated() -> None:
    assert ".claude/metrics/review-value.jsonl" in ORCHESTRATION_BENCHMARK


def test_plan_skill_both_config_changelog_occurrences_relocated() -> None:
    occurrences = [
        m.start() for m in re.finditer(r"config-changelog\.jsonl", PLAN_SKILL)
    ]
    assert len(occurrences) >= 2
    for idx in occurrences:
        window = PLAN_SKILL[max(0, idx - 20) : idx + len("config-changelog.jsonl")]
        assert ".claude/metrics/config-changelog.jsonl" in window


def test_quality_gate_pipeline_memory_reference_relocated() -> None:
    assert "re-read from .claude/memory/" in QUALITY_GATE


def test_session_review_pending_review_reads_relocated() -> None:
    assert ".claude/metrics/pending-review.jsonl" in SESSION_REVIEW
    assert "metrics/pending-review.jsonl" not in SESSION_REVIEW.replace(
        ".claude/metrics/pending-review.jsonl", ""
    )


def test_session_review_own_scratch_state_deliberately_left_bare() -> None:
    # /session-review is out of scope (plan Step 5.11) — no confirmed migration
    assert "-o memory/session-digest.json" in SESSION_REVIEW
    assert "--append metrics/session-digest.jsonl" in SESSION_REVIEW


def test_ship_skill_review_value_analogy_relocated() -> None:
    assert "convention as `.claude/metrics/review-value.jsonl`" in SHIP_SKILL


def test_test_audit_disable_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(TEST_AUDIT_DISABLE)
