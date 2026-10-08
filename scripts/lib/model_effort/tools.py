"""Resolve which tools the A/B harness gives an agent.

The harness runs each agent with its read-only built-in tools only. Every
other `tools:` entry is withheld (recorded, never enabled), and agents that
can modify files are refused because the harness has no sandbox for them.
Classification works on the `tools:` line or parsed frontmatter; it does no
file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .agent_file import AgentFrontmatterError

READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob"})
# Exact names only: a scoped entry such as `Bash(graphify *)` is withheld, not refused.
REFUSED_TOOLS = frozenset({"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"})
TOOLS_KEY = "tools"


class WriteCapableAgentError(ValueError):
    """The agent declares tools that can modify files."""


@dataclass(frozen=True)
class ToolProfile:
    enabled_tools: tuple[str, ...]
    withheld_tools: tuple[str, ...]
    refused_tools: tuple[str, ...]


def classify_tools(tools_line: str | None) -> ToolProfile:
    """Split a comma-separated `tools:` value into enabled, withheld and refused entries."""
    entries = [entry.strip() for entry in (tools_line or "").split(",")]
    named = [entry for entry in entries if entry]
    return ToolProfile(
        enabled_tools=tuple(e for e in named if e in READ_ONLY_TOOLS),
        withheld_tools=tuple(
            e for e in named if e not in READ_ONLY_TOOLS and e not in REFUSED_TOOLS
        ),
        refused_tools=tuple(e for e in named if e in REFUSED_TOOLS),
    )


def resolve_tool_profile(agent: str, frontmatter: dict) -> ToolProfile:
    """Return the tool profile for an agent's parsed frontmatter.

    Raises:
        AgentFrontmatterError: `tools:` is present but not a comma-separated string.
        WriteCapableAgentError: the agent declares an unscoped write-capable tool.
    """
    tools_line = frontmatter.get(TOOLS_KEY)
    if tools_line is not None and not isinstance(tools_line, str):
        raise AgentFrontmatterError(
            f"agent {agent!r}: `tools:` must be a comma-separated string, "
            f"got {type(tools_line).__name__}"
        )
    profile = classify_tools(tools_line)
    if profile.refused_tools:
        raise WriteCapableAgentError(
            f"agent {agent!r} declares write-capable tools "
            f"({', '.join(profile.refused_tools)}): "
            "write-capable agents are not supported yet"
        )
    return profile
