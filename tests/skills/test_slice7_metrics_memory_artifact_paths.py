"""Content-guard: remaining bare metrics/ and memory/ writer-target
references identified by Slice 7's live sweep resolve to their .claude/-
nested equivalents (plan opt-in-metrics-and-claude-scoped-artifacts.md,
Slice 7, Step 7.2).

Covers agent-eval/SKILL.md, autoship/SKILL.md, code-review/SKILL.md +
output-format.md (override-audit.jsonl only — the reports-domain content in
these two files was already handled by Slice 9's sweep and is untouched
here), context-loading-protocol/SKILL.md, and continue/SKILL.md.

metrics/verify-log.jsonl (AC3) and the bare plans/ references belonging to
/plan's own operator-facing implementation-plan-file convention are
deliberately excluded from every assertion below.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

AGENT_EVAL = (PLUGIN_ROOT / "skills" / "agent-eval" / "SKILL.md").read_text(
    encoding="utf-8"
)
AUTOSHIP = (PLUGIN_ROOT / "skills" / "autoship" / "SKILL.md").read_text(
    encoding="utf-8"
)
CODE_REVIEW = (PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text(
    encoding="utf-8"
)
OUTPUT_FORMAT = (
    PLUGIN_ROOT / "skills" / "code-review" / "output-format.md"
).read_text(encoding="utf-8")
CONTEXT_LOADING = (
    PLUGIN_ROOT / "skills" / "context-loading-protocol" / "SKILL.md"
).read_text(encoding="utf-8")
CONTINUE_SKILL = (PLUGIN_ROOT / "skills" / "continue" / "SKILL.md").read_text(
    encoding="utf-8"
)

_BARE_METRICS_RE = re.compile(r"(?<!\.claude/)metrics/(?!verify-log\.jsonl)")
_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")


def test_agent_eval_ablation_and_variance_paths_relocated() -> None:
    assert not _BARE_METRICS_RE.search(AGENT_EVAL)
    assert ".claude/metrics/eval-ablation.jsonl" in AGENT_EVAL
    assert ".claude/metrics/eval-variance.jsonl" in AGENT_EVAL
    assert ".claude/memory/eval-variance.json" in AGENT_EVAL
    # the unrelated .claude/evals/reports/ convention is untouched
    assert ".claude/evals/reports/" in AGENT_EVAL


def test_autoship_review_value_and_autoship_log_paths_relocated() -> None:
    assert ".claude/metrics/review-value.jsonl" in AUTOSHIP
    assert ".claude/metrics/autoship-log.jsonl" in AUTOSHIP
    # verify-log.jsonl stays bare (AC3)
    assert "metrics/verify-log.jsonl" in AUTOSHIP
    assert not _BARE_METRICS_RE.search(AUTOSHIP)


def test_code_review_override_audit_relocated() -> None:
    assert ".claude/metrics/override-audit.jsonl" in CODE_REVIEW
    assert "metrics/override-audit.jsonl" not in CODE_REVIEW.replace(
        ".claude/metrics/override-audit.jsonl", ""
    )


def test_output_format_override_audit_relocated() -> None:
    assert ".claude/metrics/override-audit.jsonl" in OUTPUT_FORMAT


def test_context_loading_protocol_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(CONTEXT_LOADING)
    assert ".claude/memory/" in CONTEXT_LOADING


def test_continue_skill_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(CONTINUE_SKILL)
    assert '.claude/memory/decisions.md' in CONTINUE_SKILL
    # the /plan-domain reference stays bare — a different concept
    assert '`plans/` directory for active plan files' in CONTINUE_SKILL
