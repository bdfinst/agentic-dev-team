"""Prose-presence checks for the three-tool code-intelligence comparison doc (#1108).

The doc must describe CodeGraph, Repowise, and Graphify, name Repowise's tools,
state the Read/Grep/Glob fallback, and keep its filename stable so the agents and
skills that reference it by name still resolve.
"""

from __future__ import annotations

import importlib.util

from _repo_root import REPO_ROOT

DOC = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "codegraph-vs-graphify.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
NUDGE_HOOK_PATH = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "code_intelligence_nudge.py"
)


def _load_nudge_hook_module():
    """Load code_intelligence_nudge.py directly so this test reads its
    _CUES dict off the live module, never a copy that can silently drift."""
    spec = importlib.util.spec_from_file_location(
        "code_intelligence_nudge", NUDGE_HOOK_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _cue_entry_point(tool: str, cue: str) -> str:
    """Extract the tool's entry-point name from its _CUES prose.

    Each cue is `"<entry-point stuff> — <what it's for>"`. graphify's
    entry point is its two-word CLI invocation; repowise's cue lists
    several slash-separated tool names, of which the first is the one the
    doc must mention; codegraph's cue is the bare entry-point name.
    """
    head = cue.split("—")[0].strip()
    if tool == "graphify":
        return " ".join(head.split()[:2])
    if tool == "repowise":
        after_prefix = head.split(" ", 1)[1] if " " in head else head
        return after_prefix.split("/")[0].strip()
    return head


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


def test_doc_mentions_repowise_health_and_dead_code_tools():
    text = _text()
    for tool in ("get_overview", "get_answer", "get_health", "get_dead_code"):
        assert tool in text, f"doc does not mention Repowise tool {tool}"


def test_doc_has_routing_precedence_section():
    assert "Routing precedence" in _text()


def test_doc_ties_to_hook_cues_entry_points():
    """Regression guard: each tool's current entry-point name, read live off
    the hook's own _CUES dict (not a hardcoded paraphrase), must appear
    somewhere in the doc — so a future _CUES edit that isn't mirrored here
    fails loudly instead of drifting silently (#1368)."""
    module = _load_nudge_hook_module()
    text = _text()
    for tool, cue in module._CUES.items():
        entry_point = _cue_entry_point(tool, cue)
        assert entry_point, f"could not derive an entry point for {tool}"
        assert entry_point in text, (
            f"doc does not mention {tool}'s current entry point {entry_point!r} "
            f"(from _CUES[{tool!r}] = {cue!r})"
        )


def test_doc_states_fallback_and_optionality():
    text = _text()
    assert "Read" in text and "Grep" in text and "Glob" in text
    assert "inert" in text  # grant inert when the server/CLI is absent


def test_doc_flags_repowise_server_name_coupling():
    assert "mcp__plugin_repowise_repowise__" in _text()


def test_doc_mentions_current_codegraph_explore_tool():
    assert "codegraph_explore" in _text()


def test_doc_has_no_retired_codegraph_multi_tool_names():
    text = _text()
    for retired in (
        "codegraph_context",
        "codegraph_callers",
        "codegraph_callees",
        "codegraph_impact",
    ):
        assert retired not in text, f"doc still references retired tool {retired}"


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
