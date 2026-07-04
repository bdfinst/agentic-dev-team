"""Verifies plugins/dev-team/skills/cd-test-architecture/SKILL.md is wired
for stack-aware reference loading per
plans/stack-aware-reference-loading.md (Slice 2, issue #524).

Pattern source: plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62.

Ported from tests/bats/stack-aware-cd-test-architecture.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _stack_aware_helpers import BANNED_TOKENS_RE, body_only

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "cd-test-architecture" / "SKILL.md"
)


def _section(text: str, start_pattern: str, end_pattern: str = r"^## ") -> str:
    lines = text.splitlines()
    collected = []
    on = False
    for line in lines:
        if re.match(start_pattern, line):
            on = True
            continue
        if on and re.match(end_pattern, line):
            on = False
        if on:
            collected.append(line)
    return "\n".join(collected)


@pytest.fixture(scope="module")
def text() -> str:
    return TARGET.read_text(encoding="utf-8")


def test_names_test_stack_profiles_and_cross_references_test_design_advisor(
    text: str,
) -> None:
    assert "test-stack-profiles" in text
    assert "test-design-advisor" in text


def test_lists_all_six_manifest_tokens_for_stack_detection(text: str) -> None:
    assert "package.json" in text
    assert re.search(r"\.csproj", text)
    assert re.search(r"pom\.xml|build\.gradle", text)
    assert "go.mod" in text
    assert re.search(r"pyproject\.toml|requirements\.txt", text)
    assert "htmx" in text


def test_documents_missing_profile_fallback_phrase(text: str) -> None:
    assert "name the missing profile" in text


def test_documents_stack_flag_within_parse_arguments_section(text: str) -> None:
    # Slice the file from '## Parse Arguments' to the next '## ' heading,
    # then assert --stack appears in that block.
    section = _section(text, r"^## Parse Arguments")
    assert "--stack" in section


def test_states_stack_flag_takes_precedence_over_manifest_detection(
    text: str,
) -> None:
    # Range starts on the line AFTER the 'Detect stack' heading and ends at
    # the next '### ' heading.
    block = _section(text, r"^### .*Detect stack", r"^### ")
    assert re.search(
        r"takes precedence|overrides|skips detection|wins over", block, re.IGNORECASE
    )


def test_target_architecture_schema_requires_citing_loaded_profile(
    text: str,
) -> None:
    block = _section(text, r"^### Target architecture", r"^### ")
    assert re.search(
        r"cite.*profile|profile.*cite|test-stack-profiles", block, re.IGNORECASE
    )


def test_body_contains_no_language_specific_tokens(text: str) -> None:
    stripped = body_only(text)
    assert not BANNED_TOKENS_RE.search(stripped)
