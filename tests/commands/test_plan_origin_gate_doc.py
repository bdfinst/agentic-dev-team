"""#226 — /plan step 6 must gate GitHub issue creation on a GitHub origin:
classify via git_origin_host.py, prompt only on github, show the count,
default No, consent-gate /issues-from-plan, and skip non-interactively. Doc
gate.

Ported from tests/commands/plan_origin_gate_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "plan" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_step_6_classifies_origin_via_git_origin_host(text: str) -> None:
    assert "git_origin_host.py" in text


def test_prompts_only_on_github_origin(text: str) -> None:
    assert re.search(
        r"github.*origin only|GitHub origin only|"
        r"only.*offer issue creation on an actual GitHub host",
        text,
        re.IGNORECASE,
    )


def test_shows_issue_count_in_prompt(text: str) -> None:
    assert "parent issue and n linked" in text.lower()


def test_default_is_no(text: str) -> None:
    assert "[y/N]" in text
    lowered = text.lower()
    assert "default is **no**" in lowered or "default is no" in lowered


def test_invokes_issues_from_plan_only_on_explicit_consent(text: str) -> None:
    assert "only on explicit" in text.lower()
    assert "issues-from-plan" in text


def test_other_none_origins_do_not_prompt(text: str) -> None:
    assert "no prompt" in text.lower()


def test_non_interactive_skips_without_blocking(text: str) -> None:
    lowered = text.lower()
    assert "non-interactive" in lowered
    assert "skipping the github issue prompt" in lowered
