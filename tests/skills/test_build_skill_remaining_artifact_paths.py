"""Content-guard: skills/build/SKILL.md's remaining bare metrics/memory/plans
references — missed by earlier slices' partial passes — resolve to their
.claude/-nested equivalents (Slice 7, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

Slice 5's Step 5.7 was checked off for updating build_slice_scope.py's
bookkeeping allowlist *and* build/SKILL.md's matching prose paragraph, but
only the script was actually fixed — the "Slice dispatch bookkeeping"
paragraph's `memory/**`/`metrics/**` literals, plus several other independent
references (the rollback-point --path value, the build-escalation record
path, and one approval-entry mention), were still bare. This test pins the
fix live-discovered during Slice 7's sweep.

metrics/verify-log.jsonl (AC3) and the bare plans/ references belonging to
/plan's own operator-facing implementation-plan-file convention (a distinct
concept from this epic's .claude/plans/ runtime-state domain) are
deliberately excluded — see plan/SKILL.md's own precedent.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

BUILD_SKILL = (PLUGIN_ROOT / "skills" / "build" / "SKILL.md").read_text(
    encoding="utf-8"
)


def test_bookkeeping_allowlist_prose_matches_the_relocated_script_patterns() -> None:
    assert ".claude/memory/**" in BUILD_SKILL
    assert ".claude/metrics/**" in BUILD_SKILL
    # the stale bare-literal pair must not remain anywhere as a parenthesized pair
    assert "(the plan file, `memory/**`, `metrics/**`)" not in BUILD_SKILL


def test_rollback_point_path_is_claude_scoped() -> None:
    assert ".claude/memory/build-rollback.json" in BUILD_SKILL
    assert "--path memory/build-rollback.json" not in BUILD_SKILL


def test_build_escalation_record_path_is_claude_scoped() -> None:
    assert ".claude/memory/build-escalation-<plan-slug>.md" in BUILD_SKILL
    assert "to `memory/build-escalation-<plan-slug>.md`" not in BUILD_SKILL


def test_review_value_schema_reference_is_claude_scoped() -> None:
    assert (
        "schema modeled on `.claude/metrics/review-value.jsonl`" in BUILD_SKILL
    )


def test_verify_log_stays_bare_per_ac3_exemption() -> None:
    assert "metrics/verify-log.jsonl" in BUILD_SKILL


def test_no_other_bare_memory_reference_remains_outside_exemptions() -> None:
    # Every remaining bare `memory/` occurrence must be the pre-existing
    # in-context-state contrast ("This is not a `memory/` file") — no
    # additional stray bare memory/ paths should appear.
    bare_memory = re.findall(r"(?<!\.claude/)memory/[A-Za-z0-9_.<>-]*", BUILD_SKILL)
    unexpected = [m for m in bare_memory if m != "memory/"]
    assert not unexpected, f"unexpected bare memory/ path(s): {unexpected}"
