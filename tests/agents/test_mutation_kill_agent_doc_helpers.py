"""Contract for the shared `_mutation_kill_agent_doc_helpers` module (#1927,
plan slice 1, steps 1.1-1.2): `AGENT`, `agent_text()`, and
`required_section()`.
"""

from __future__ import annotations

import pytest
from _mutation_kill_agent_doc_helpers import AGENT, agent_text, required_section

from _repo_root import REPO_ROOT


def test_agent_resolves_to_mutation_kill_md() -> None:
    assert AGENT == REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"
    assert AGENT.is_file()


def test_agent_text_returns_full_file_content() -> None:
    assert agent_text() == AGENT.read_text(encoding="utf-8")


def test_required_section_returns_matched_section() -> None:
    text = agent_text()
    result = required_section(
        text,
        r"^## Pre-loop feasibility gate",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Pre-loop feasibility gate",
    )
    assert result


def test_required_section_raises_with_given_name_when_missing() -> None:
    with pytest.raises(AssertionError, match="Some Section"):
        required_section(
            "no matching heading here",
            r"^## Does Not Exist",
            name="Some Section",
        )


def test_required_section_raises_with_some_message_when_name_omitted() -> None:
    with pytest.raises(AssertionError):
        required_section("no matching heading here", r"^## Does Not Exist")
