"""Resolve which tools the A/B harness gives an agent.

The harness runs each agent with its read-only built-in tools only. Every
other `tools:` entry is withheld (recorded, never enabled), and agents that
can modify files are refused because the harness has no sandbox for them.

Requires `plugins/dev-team/hooks/lib/` on sys.path (for `minimal_yaml`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from minimal_yaml import (
    FrontmatterError,
    YamlError,
    extract_frontmatter_block,
    parse_yaml,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"

ENABLED_TOOLS = frozenset({"Read", "Grep", "Glob"})
# Exact names only: a scoped entry such as `Bash(graphify *)` is withheld, not refused.
WRITE_CAPABLE_TOOLS = frozenset({"Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"})
TOOLS_KEY = "tools"


class UnknownAgentError(LookupError):
    """No agent file exists for the requested agent name."""


class AgentFrontmatterError(ValueError):
    """An agent file's frontmatter cannot be read."""


class WriteCapableAgentError(ValueError):
    """The agent declares tools that can modify files."""


@dataclass(frozen=True)
class ToolProfile:
    enabled: tuple[str, ...]
    withheld: tuple[str, ...]
    refused: tuple[str, ...]

    @property
    def has_enabled_tools(self) -> bool:
        return bool(self.enabled)


def classify_tools(tools_line: str | None) -> ToolProfile:
    """Split a comma-separated `tools:` value into enabled, withheld and refused entries."""
    entries = [entry.strip() for entry in (tools_line or "").split(",")]
    named = [entry for entry in entries if entry]
    return ToolProfile(
        enabled=tuple(e for e in named if e in ENABLED_TOOLS),
        withheld=tuple(
            e for e in named if e not in ENABLED_TOOLS and e not in WRITE_CAPABLE_TOOLS
        ),
        refused=tuple(e for e in named if e in WRITE_CAPABLE_TOOLS),
    )


def list_agent_names(agents_dir: Path = AGENTS_DIR) -> list[str]:
    return sorted(path.stem for path in agents_dir.glob("*.md"))


def load_tool_profile(agent: str, agents_dir: Path = AGENTS_DIR) -> ToolProfile:
    """Return the tool profile for `agent`, or raise if it is unknown or write-capable."""
    valid_names = list_agent_names(agents_dir)
    if agent not in valid_names:
        raise UnknownAgentError(
            f"unknown agent {agent!r}: no agent file in {agents_dir}. "
            f"Valid agents: {', '.join(valid_names)}"
        )
    profile = classify_tools(_read_tools_line(agent, agents_dir / f"{agent}.md"))
    if profile.refused:
        raise WriteCapableAgentError(
            f"agent {agent!r} declares write-capable tools ({', '.join(profile.refused)}): "
            "write-capable agents are not supported yet"
        )
    return profile


def _read_tools_line(agent: str, agent_file: Path) -> str | None:
    try:
        frontmatter = parse_yaml(
            extract_frontmatter_block(agent_file.read_text(encoding="utf-8"))
        )
    except (FrontmatterError, YamlError) as error:
        raise AgentFrontmatterError(
            f"cannot read frontmatter of agent {agent!r} ({agent_file}): {error}"
        ) from error
    tools_line = frontmatter.get(TOOLS_KEY) if isinstance(frontmatter, dict) else None
    if tools_line is not None and not isinstance(tools_line, str):
        raise AgentFrontmatterError(
            f"agent {agent!r} ({agent_file}): `tools:` must be a comma-separated string, "
            f"got {type(tools_line).__name__}"
        )
    return tools_line
