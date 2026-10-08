"""Read an agent file's baseline model, effort and system prompt.

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

from .tools import AgentFrontmatterError

FRONTMATTER_CLOSE = "\n---"


@dataclass(frozen=True)
class AgentSpec:
    model: str
    effort: str
    system_prompt: str


def load_agent_spec(agent: str, agents_dir: Path) -> AgentSpec:
    """Return the agent's frontmatter `model:`/`effort:` and its body as the system prompt."""
    agent_file = agents_dir / f"{agent}.md"
    text = agent_file.read_text(encoding="utf-8")
    try:
        block = extract_frontmatter_block(text)
        frontmatter = parse_yaml(block)
    except (FrontmatterError, YamlError) as error:
        raise AgentFrontmatterError(
            f"cannot read frontmatter of agent {agent!r} ({agent_file}): {error}"
        ) from error
    fields = frontmatter if isinstance(frontmatter, dict) else {}
    body_start = 3 + len(block) + len(FRONTMATTER_CLOSE)
    return AgentSpec(
        model=_required_text(fields, "model", agent, agent_file),
        effort=_required_text(fields, "effort", agent, agent_file),
        system_prompt=text[body_start:].lstrip("\n"),
    )


def _required_text(fields: dict, key: str, agent: str, agent_file: Path) -> str:
    value = fields.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentFrontmatterError(
            f"agent {agent!r} ({agent_file}) has no `{key}:` in its frontmatter, so "
            "the baseline arm is undefined"
        )
    return value.strip()
