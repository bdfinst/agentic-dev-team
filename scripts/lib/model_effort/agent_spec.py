"""An agent's baseline model, effort and system prompt, from its loaded file."""

from __future__ import annotations

from dataclasses import dataclass

from .agent_file import AgentFile, AgentFrontmatterError


@dataclass(frozen=True)
class AgentSpec:
    model: str
    effort: str
    system_prompt: str


def build_agent_spec(agent: str, agent_file: AgentFile) -> AgentSpec:
    """Return the frontmatter `model:`/`effort:` with the file body as the system prompt.

    Raises:
        AgentFrontmatterError: `model:` or `effort:` is missing or blank.
    """
    return AgentSpec(
        model=_required_text(agent, agent_file, "model"),
        effort=_required_text(agent, agent_file, "effort"),
        system_prompt=agent_file.body,
    )


def _required_text(agent: str, agent_file: AgentFile, key: str) -> str:
    value = agent_file.frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentFrontmatterError(
            f"agent {agent!r} ({agent_file.path}) has no `{key}:` in its frontmatter, "
            "so the baseline arm is undefined"
        )
    return value.strip()
