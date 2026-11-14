"""Resolve which tools the A/B harness gives an agent.

The harness runs each agent with its read-only built-in tools. An agent the
grader map marks `sandbox` also gets its write tools, because each trial runs in
a temp copy of the fixture; any other agent that can modify files is refused. A
dispatch-graded agent also gets its `Agent` tool, so its dispatches show in the
transcript. Every other `tools:` entry is withheld (recorded, never enabled).
Classification works on the `tools:` line or parsed frontmatter; it does no
file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .agent_file import AgentFrontmatterError

READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob"})
# Exact names only: a scoped entry such as `Bash(graphify *)` is withheld, not refused.
REFUSED_TOOLS = frozenset({"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"})
DISPATCH_TOOLS = frozenset({"Agent", "Task"})
TOOLS_KEY = "tools"


class WriteCapableAgentError(ValueError):
    """The agent declares tools that can modify files."""


@dataclass(frozen=True)
class ToolProfile:
    enabled_tools: tuple[str, ...]
    withheld_tools: tuple[str, ...]
    refused_tools: tuple[str, ...]


def classify_tools(
    tools_line: str | None, *, sandbox: bool = False, dispatch: bool = False
) -> ToolProfile:
    """Split a comma-separated `tools:` value into enabled, withheld and refused entries.

    `sandbox` enables the write tools instead of refusing them; `dispatch`
    enables the `Agent` tool instead of withholding it.
    """
    entries = [entry.strip() for entry in (tools_line or "").split(",")]
    named = [entry for entry in entries if entry]
    enabled = set(READ_ONLY_TOOLS)
    if sandbox:
        enabled |= REFUSED_TOOLS
    if dispatch:
        enabled |= DISPATCH_TOOLS
    return ToolProfile(
        enabled_tools=tuple(e for e in named if e in enabled),
        withheld_tools=tuple(
            e for e in named if e not in enabled and e not in REFUSED_TOOLS
        ),
        refused_tools=tuple(e for e in named if e in REFUSED_TOOLS and e not in enabled),
    )


def resolve_tool_profile(
    agent: str, frontmatter: dict, *, sandbox: bool = False, dispatch: bool = False
) -> ToolProfile:
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
    profile = classify_tools(tools_line, sandbox=sandbox, dispatch=dispatch)
    if profile.refused_tools:
        raise WriteCapableAgentError(
            f"agent {agent!r} declares write-capable tools "
            f"({', '.join(profile.refused_tools)}): "
            "a write-capable agent runs only when evals/model-effort/graders.json "
            "marks it `sandbox: true`"
        )
    return profile
