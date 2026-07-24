"""Skills dispatched by /test-design must be invoked via the Skill tool,
not Agent. Regression guard for: "Agent type 'dev-team:test-design-advisor'
not found"

Ported from tests/docs/test_design_skill_dispatch_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_test_design_advisor_dispatched_with_skill_tool_not_agent(
    text: str,
) -> None:
    assert "Skill(test-design-advisor" in text


def test_farley_score_dispatched_with_skill_tool_not_agent(text: str) -> None:
    assert "Skill(farley-score" in text


def test_test_design_advisor_not_dispatched_with_bare_invoke_wording(
    text: str,
) -> None:
    assert "invoke the `test-design-advisor`" not in text.lower()


def test_farley_score_not_dispatched_with_bare_invoke_wording(text: str) -> None:
    assert "invoke the `farley-score`" not in text.lower()
