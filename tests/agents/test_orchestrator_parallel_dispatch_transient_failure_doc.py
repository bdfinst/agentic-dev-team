"""Documentation gate for issue #1609 — the orchestrator's parallel
implementation-dispatch guidance must warn that disjoint *final* file sets
are not sufficient to skip worktree isolation, and must state the fallback
(re-verify after all parallel subagents complete) for dispatches that skip
isolation anyway.

Hermetic: this suite is a read-only check against a checked-in file; no git
ops, no fs mutation.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"


def _text() -> str:
    return ORCH.read_text(encoding="utf-8")


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
