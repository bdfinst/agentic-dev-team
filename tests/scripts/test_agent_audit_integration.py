"""Pins agent-audit's SKILL.md wiring to the Python review scripts, not the
retired agent-dispatch pattern.

Ported from tests/scripts/agent_audit_integration_tests.bats (issue #676).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-audit" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_agent_audit_skill_references_claude_setup_review_py() -> None:
    assert "scripts/claude_setup_review.py" in _text()


def test_agent_audit_skill_references_token_efficiency_review_py() -> None:
    assert "scripts/token_efficiency_review.py" in _text()


def test_agent_audit_skill_does_not_dispatch_claude_setup_review_agent() -> None:
    assert not re.search(r"(dispatch|Agent:)\s+claude-setup-review", _text())


def test_agent_audit_skill_does_not_dispatch_token_efficiency_review_agent() -> None:
    assert not re.search(r"(dispatch|Agent:)\s+token-efficiency-review", _text())


def test_agent_audit_skill_references_review_agent_mcp_check() -> None:
    assert "scripts/check_review_agent_mcp_tools.py" in _text()


def test_agent_audit_skill_references_agent_tool_mapping_check() -> None:
    # #1108: the non-review mapping invariant must be wired into agent-audit.
    assert "scripts/check_agent_tool_mapping.py" in _text()
