"""Content-guard: the multi-workflow worker skills (coverage-baseline,
coverage-delta, gherkin-derive, gherkin-public, quality-targets-converge)
resolve their generic `<workflow>`-templated memory/plans paths under
`.claude/` (Slice 7, plan opt-in-metrics-and-claude-scoped-artifacts.md).

Also covers governance-compliance/SKILL.md and feedback-learning/SKILL.md's
remaining bare metrics/memory references left over from the code-review fix
pass, which scoped its edits to config-changelog.jsonl/review-value.jsonl
only.

`metrics/session-digest.jsonl` (feedback-learning/SKILL.md) is deliberately
excluded — the plan's Step 5.11 explicitly names it (alongside
eval-ablation.jsonl) as written by an out-of-scope workflow (/session-review)
with no confirmed migration, unlike eval-variance.jsonl which Slice 6
concretely relocated.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

COVERAGE_BASELINE = (
    PLUGIN_ROOT / "skills" / "coverage-baseline" / "SKILL.md"
).read_text(encoding="utf-8")
COVERAGE_DELTA = (PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md").read_text(
    encoding="utf-8"
)
GHERKIN_DERIVE = (PLUGIN_ROOT / "skills" / "gherkin-derive" / "SKILL.md").read_text(
    encoding="utf-8"
)
GHERKIN_PUBLIC = (PLUGIN_ROOT / "skills" / "gherkin-public" / "SKILL.md").read_text(
    encoding="utf-8"
)
GOVERNANCE = (
    PLUGIN_ROOT / "skills" / "governance-compliance" / "SKILL.md"
).read_text(encoding="utf-8")
FEEDBACK_LEARNING = (
    PLUGIN_ROOT / "skills" / "feedback-learning" / "SKILL.md"
).read_text(encoding="utf-8")

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")
_BARE_METRICS_RE = re.compile(r"(?<!\.claude/)metrics/(?!session-digest\.jsonl)")
_BARE_PLANS_WORKFLOW_RE = re.compile(r"(?<!\.claude/)plans/<workflow>")


def test_coverage_baseline_has_no_bare_memory_or_plans_workflow_reference() -> None:
    assert not _BARE_MEMORY_RE.search(COVERAGE_BASELINE)
    assert not _BARE_PLANS_WORKFLOW_RE.search(COVERAGE_BASELINE)


def test_coverage_delta_has_no_bare_memory_or_plans_workflow_reference() -> None:
    assert not _BARE_MEMORY_RE.search(COVERAGE_DELTA)
    assert not _BARE_PLANS_WORKFLOW_RE.search(COVERAGE_DELTA)


def test_gherkin_derive_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(GHERKIN_DERIVE)


def test_gherkin_public_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(GHERKIN_PUBLIC)


def test_governance_compliance_has_no_bare_metrics_or_memory_reference() -> None:
    assert not _BARE_METRICS_RE.search(GOVERNANCE)
    assert not _BARE_MEMORY_RE.search(GOVERNANCE)


def test_feedback_learning_pending_review_and_prose_memory_relocated() -> None:
    assert ".claude/metrics/pending-review.jsonl" in FEEDBACK_LEARNING
    assert "metrics/pending-review.jsonl" not in FEEDBACK_LEARNING.replace(
        ".claude/metrics/pending-review.jsonl", ""
    )
    assert not _BARE_MEMORY_RE.search(FEEDBACK_LEARNING)


def test_feedback_learning_session_digest_deliberately_left_bare() -> None:
    # /session-review is out of scope per the plan's Step 5.11 — no confirmed
    # migration of this specific file, unlike eval-variance.jsonl.
    assert "metrics/session-digest.jsonl" in FEEDBACK_LEARNING
