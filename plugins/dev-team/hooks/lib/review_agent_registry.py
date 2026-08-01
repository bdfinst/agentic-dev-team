"""hooks/lib/review_agent_registry.py — shared *-review agent glob discovery (#1461).

Both `scripts/check_review_agent_mcp_tools.py` (MCP tool-grant auditing) and
`hooks/agent_dispatch_ledger.py` (the dispatch-ledger PreToolUse hook, #1461)
need the same closed set of registered review-agent names: every
`agents/*-review.md` file's stem. This module is the single extraction point
so a hook never reaches into `scripts/` — the correct dependency direction is
`scripts/` -> `hooks/lib/`, never the reverse (a hook must be import-safe
without any `scripts/` module on its path).

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

from pathlib import Path

# This plugin's own marketplace-qualified prefix. A real Agent-tool dispatch
# of one of this plugin's registered review agents, once installed, is named
# "dev-team:<agent-name>" (e.g. "dev-team:doc-review") — the closed set below
# is built from bare `agents/*-review.md` file stems, so an unstripped
# qualified name never matches it (#1461 follow-up: this silently dropped
# every dispatch's ledger record for the plugin's normal, installed
# invocation form). A prefix for a DIFFERENT plugin is left untouched — it
# is never one of this registry's own agents.
_PLUGIN_PREFIX = "dev-team:"


def strip_plugin_prefix(subagent_type: str) -> str:
    """Normalize a dispatch's `subagent_type` to the bare agent name this
    registry's closed set uses, stripping only this plugin's own
    `dev-team:` qualifier."""
    if subagent_type.startswith(_PLUGIN_PREFIX):
        return subagent_type[len(_PLUGIN_PREFIX) :]
    return subagent_type


def find_review_agent_files(agents_dir: Path) -> list[Path]:
    """Return the read-only review agent files (agents/*-review.md), sorted.

    Glob-discovery logic extracted verbatim from
    `scripts/check_review_agent_mcp_tools.py::find_review_agents` (#1461) —
    behavior-identical, so existing callers/tests of that function regress
    against this implementation unchanged.
    """
    return sorted(Path(agents_dir).glob("*-review.md"))


def registered_review_agent_names(agents_dir: Path) -> frozenset[str]:
    """Return the closed set of registered review-agent names (file stems).

    This is the authoritative closed vocabulary `hooks/agent_dispatch_ledger.py`
    checks an Agent-tool dispatch's `subagent_type` against before recording a
    ledger event — a name outside this set is never a real review agent, and
    is never written to the ledger, not even as a rejected/flagged entry.
    """
    return frozenset(path.stem for path in find_review_agent_files(agents_dir))
