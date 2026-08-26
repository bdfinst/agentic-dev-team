"""Documentation gate for issue #1609 — the orchestrator's parallel
implementation-dispatch guidance must warn that disjoint *final* file sets
are not sufficient to skip worktree isolation, and must state the fallback
(re-verify after all parallel subagents complete) for dispatches that skip
isolation anyway.

The guidance now lives in `knowledge/three-phase-workflow.md` § Phase 3:
Implement, which `agents/orchestrator.md` loads on demand (#2011 — the
orchestrator's body is always-on context, so per-phase detail moved behind
the knowledge index). The assertions therefore run against the knowledge
file, plus one that pins the orchestrator's pointer at it so the on-demand
path still resolves.

Hermetic: this suite is a read-only check against checked-in files; no git
ops, no fs mutation.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
ORCH = PLUGIN / "agents" / "orchestrator.md"
PHASES = PLUGIN / "knowledge" / "three-phase-workflow.md"


def _text() -> str:
    return PHASES.read_text(encoding="utf-8")


def test_orchestrator_still_recommends_worktree_isolation_for_parallel_units() -> None:
    text = _text()
    assert 'isolation: "worktree"' in text


def test_orchestrator_warns_disjoint_final_files_are_not_sufficient() -> None:
    text = _text()
    assert "mid-edit" in text or "intermediate" in text


def test_orchestrator_states_the_reverify_after_completion_fallback() -> None:
    text = _text()
    assert "re-verify" in text.lower()
    assert "timing artifact" in text.lower() or "provisional" in text.lower()


def test_orchestrator_references_issue_1609() -> None:
    text = _text()
    assert "#1609" in text


def test_orchestrator_points_at_the_phase_3_section_carrying_this_guidance() -> None:
    # The on-demand path: the always-on agent body must name the exact
    # anchor a session resolves to reach the guidance above.
    orch = ORCH.read_text(encoding="utf-8")
    assert (
        "${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#phase-3-implement"
        in orch
    )
