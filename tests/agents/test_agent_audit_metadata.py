"""Ported from tests/agents/agent_audit_metadata_tests.bats (issue #675)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "plugins" / "dev-team" / "agents"


def test_claude_setup_review_has_context_needs_project_structure() -> None:
    text = (AGENTS / "claude-setup-review.md").read_text(encoding="utf-8")
    assert "Context needs: project-structure" in text


def test_orchestrator_declares_enforcement_script_and_implemented_by() -> None:
    # The orchestrator was converted to a script-enforced prose spec (PR #462):
    # it is no longer a persona-driven team agent, so instead of a "You are"
    # persona it declares `enforcement: script` and points at its
    # implementation.
    text = (AGENTS / "orchestrator.md").read_text(encoding="utf-8")
    assert re.search(r"^enforcement:\s*script", text, re.MULTILINE)
    assert re.search(r"^> \*\*Implemented by:\*\*", text, re.MULTILINE)
