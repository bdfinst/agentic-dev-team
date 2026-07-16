"""Prose-presence checks for the three-tool code-intelligence comparison doc (#1108).

The doc must describe CodeGraph, Repowise, and Graphify, name Repowise's tools,
state the Read/Grep/Glob fallback, and keep its filename stable so the agents and
skills that reference it by name still resolve.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "codegraph-vs-graphify.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists_at_stable_path():
    # The filename is referenced by agents/skills; renaming would break them.
    assert DOC.is_file()


def test_doc_names_all_three_tools():
    text = _text()
    for tool in ("CodeGraph", "Repowise", "Graphify"):
        assert tool in text, f"doc does not mention {tool}"


def test_doc_names_repowise_tools():
    text = _text()
    for tool in ("get_context", "get_symbol", "search_codebase", "get_risk", "get_why"):
        assert tool in text, f"doc does not mention Repowise tool {tool}"


def test_doc_states_fallback_and_optionality():
    text = _text()
    assert "Read" in text and "Grep" in text and "Glob" in text
    assert "inert" in text  # grant inert when the server/CLI is absent


def test_doc_flags_repowise_server_name_coupling():
    assert "mcp__plugin_repowise_repowise__" in _text()


def test_referencing_agents_still_resolve_the_filename():
    # Every agent that references the doc must reference the CURRENT filename
    # (the edit must not have renamed it out from under them).
    referencing = [
        "codebase-recon",
        "architect",
        "adr-author",
        "security-engineer",
        "platform-engineer",
        "data-flow-tracer",
    ]
    for name in referencing:
        body = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert "knowledge/codegraph-vs-graphify.md" in body, name
