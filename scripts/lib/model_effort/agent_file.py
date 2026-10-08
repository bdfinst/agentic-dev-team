"""Load an agent file once: its parsed frontmatter and its body."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import external

FRONTMATTER_DELIMITER = "---"
_FRONTMATTER_PATTERN = re.compile(
    rf"\A{FRONTMATTER_DELIMITER}[ \t]*\r?\n"
    rf"(?P<block>.*?)^{FRONTMATTER_DELIMITER}[ \t\r]*$\n?"
    r"(?P<body>.*)\Z",
    re.DOTALL | re.MULTILINE,
)


class UnknownAgentError(LookupError):
    """No agent file exists for the requested agent name."""


class AgentFrontmatterError(ValueError):
    """An agent file or its frontmatter cannot be read."""


@dataclass(frozen=True)
class AgentFile:
    path: Path
    frontmatter: dict
    body: str


def list_agent_names(agents_dir: Path) -> list[str]:
    return sorted(path.stem for path in agents_dir.glob("*.md"))


def load_agent_file(agent: str, agents_dir: Path) -> AgentFile:
    """Read `agent`'s file once; return its frontmatter mapping and body.

    Raises:
        UnknownAgentError: no `<agent>.md` in `agents_dir` (names with path
            separators never match).
        AgentFrontmatterError: the file cannot be read or decoded, has no
            `---` delimited block, or the block is not a YAML mapping within
            the supported subset.
    """
    valid_names = list_agent_names(agents_dir)
    if agent not in valid_names:
        raise UnknownAgentError(
            f"unknown agent {agent!r}: no agent file in {agents_dir}. "
            f"Valid agents: {', '.join(valid_names)}"
        )
    path = agents_dir / f"{agent}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AgentFrontmatterError(
            f"cannot read agent {agent!r} ({path}): {error}"
        ) from error
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        raise AgentFrontmatterError(
            f"cannot read frontmatter of agent {agent!r} ({path}): no "
            f"`{FRONTMATTER_DELIMITER}` delimited block at the top of the file"
        )
    yaml = external.minimal_yaml()
    try:
        frontmatter = yaml.parse_yaml(match["block"])
    except yaml.YamlError as error:
        raise AgentFrontmatterError(
            f"cannot read frontmatter of agent {agent!r} ({path}): {error}"
        ) from error
    if not isinstance(frontmatter, dict):
        raise AgentFrontmatterError(
            f"cannot read frontmatter of agent {agent!r} ({path}): "
            "the block is not a key: value mapping"
        )
    return AgentFile(
        path=path, frontmatter=frontmatter, body=match["body"].lstrip("\n")
    )
