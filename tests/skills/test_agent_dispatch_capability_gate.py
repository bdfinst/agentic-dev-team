"""Content-guard: agent-dispatch capability hard-fail instructions (#1461).

`review_gate_hash()`'s hash proves the staged diff matches what was reviewed
— it cannot prove an independent review agent actually ran. That gap was
observed in production: an orchestrating agent with no Agent/Task dispatch
tool available silently self-applied review checklists inline instead of
hard-failing, then wrote a matching `.claude/memory/.review-passed` and
committed/opened a PR off a self-certified pass that a later genuine
multi-agent review showed had missed real defects (including one that would
have broken CI).

Full cryptographic hardening of the gate is out of scope (issue #1461); the
feasible mitigation is a hard, early instruction in each dispatching skill:
confirm `Agent`/`Task` tool availability before dispatching any review
agent, and STOP — no self-applied review, no `.review-passed` write — when
it is missing. This test pins that instruction's presence in the four
skills that dispatch (or, for `/ship`, delegate to skills that dispatch)
review agents.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

CODE_REVIEW = (PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text(
    encoding="utf-8"
)
PLAN = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text(encoding="utf-8")
BUILD = (PLUGIN_ROOT / "skills" / "build" / "SKILL.md").read_text(encoding="utf-8")
SHIP = (PLUGIN_ROOT / "skills" / "ship" / "SKILL.md").read_text(encoding="utf-8")


def test_code_review_hard_fails_on_missing_dispatch_capability() -> None:
    assert "issue #1461" in CODE_REVIEW
    assert "`Agent` (or `Task`) tool is actually present" in CODE_REVIEW
    assert "STOP." in CODE_REVIEW
    assert "Do not write `.review-passed`" in CODE_REVIEW


def test_plan_hard_fails_on_missing_dispatch_capability_before_step_5b() -> None:
    assert "issue #1461" in PLAN
    assert "`Agent` (or `Task`) tool is actually present" in PLAN
    assert "Step 5b" in PLAN
    assert "STOP." in PLAN


def test_build_hard_fails_on_missing_dispatch_capability_for_review_checkpoints() -> None:
    assert "issue #1461" in BUILD
    assert "`Agent` (or `Task`) tool is actually present" in BUILD
    assert "STOP" in BUILD
    # All three review-dispatch points name the gate.
    assert BUILD.count("Dispatch-capability gate (re-confirm here") >= 3


def test_ship_points_at_delegated_skills_own_gates_without_duplicating() -> None:
    assert "issue #1461" in SHIP
    assert "enforced by the delegated skills, not duplicated here" in SHIP
    # Ship's note references the same three skills' own dispatch points.
    assert "`/plan` (Step 5b)" in SHIP
    assert "`/build` (Steps 3, 4, 6)" in SHIP
    assert "`/code-review` (Step 4)" in SHIP
