"""Content-guard: remaining bare metrics/memory writer-target references in
plugins/dev-team/docs/ and cross-cutting knowledge/skill reference files
resolve to their .claude/-nested equivalents (Slice 7, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

`docs/eval-system.md`'s `evals/reports/` tree-diagram entry is the eval
runner's own scratch-output subdirectory (test data, not a real project
artifact path) and is deliberately excluded, as is its `session-digest.jsonl`
mention (/session-review is out of scope per the plan's Step 5.11).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

DOCS = REPO_ROOT / "plugins" / "dev-team" / "docs"
BUILD_REFS = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "references"

AGENT_INFO = (DOCS / "agent_info.md").read_text(encoding="utf-8")
CODE_REVIEW_PROCESS = (DOCS / "code-review-process.md").read_text(encoding="utf-8")
CONTEXT_MANAGEMENT = (DOCS / "context-management.md").read_text(encoding="utf-8")
EVAL_MAINTENANCE = (DOCS / "eval-maintenance.md").read_text(encoding="utf-8")
EVAL_RUNNING_GUIDE = (DOCS / "eval-running-guide.md").read_text(encoding="utf-8")
EVAL_SYSTEM = (DOCS / "eval-system.md").read_text(encoding="utf-8")
STATIC_SELF_HEAL = (BUILD_REFS / "static-self-heal.md").read_text(encoding="utf-8")


def test_agent_info_recon_artifact_location_relocated() -> None:
    assert "produces a RECON artifact in `.claude/memory/`" in AGENT_INFO


def test_code_review_process_audit_paths_relocated() -> None:
    assert ".claude/metrics/override-audit.jsonl" in CODE_REVIEW_PROCESS
    assert ".claude/metrics/gate-bypass-audit.jsonl" in CODE_REVIEW_PROCESS
    assert "| `metrics/override-audit.jsonl`" not in CODE_REVIEW_PROCESS
    assert "| `metrics/gate-bypass-audit.jsonl`" not in CODE_REVIEW_PROCESS


def test_context_management_full_summary_destination_relocated() -> None:
    assert "Write a full summary to `.claude/memory/`" in CONTEXT_MANAGEMENT


def test_eval_maintenance_variance_trend_relocated() -> None:
    assert EVAL_MAINTENANCE.count(".claude/metrics/eval-variance.jsonl") >= 2


def test_eval_running_guide_variance_append_relocated() -> None:
    assert "--append .claude/metrics/eval-variance.jsonl" in EVAL_RUNNING_GUIDE


def test_eval_system_task_log_stream_relocated_session_digest_stays_bare() -> None:
    assert ".claude/metrics/*-task-log.jsonl" in EVAL_SYSTEM
    assert "metrics/session-digest.jsonl" in EVAL_SYSTEM
    # the eval runner's own scratch-output tree entry is untouched
    assert re.search(r"reports/\s*#\s*Auto-created by runner", EVAL_SYSTEM)


def test_static_self_heal_review_value_relocated() -> None:
    assert ".claude/metrics/review-value.jsonl" in STATIC_SELF_HEAL
