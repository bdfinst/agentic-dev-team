"""hooks/lib/agent_skill_hints.py — resolve an agent type's declared skills
from its own frontmatter (#2187, Slice 1 Step 1.1).

`subagent_skill_context.py`'s `PreToolUse` hook (Step 1.2) needs to know
which skills a dispatched `subagent_type` is expected to load, so it can
inject a short reminder note into the dispatch prompt. Per this plan's
design note (ADR 0028), each agent's own frontmatter `skills:` field is the
single source of truth for that mapping — `knowledge/agent-registry.md`
does not mirror `skills:` per-agent, so it is not consulted here.

Reuses `minimal_yaml.py`'s `extract_frontmatter_block` + `parse_yaml`
directly rather than writing a second frontmatter parser — that module
already parses this exact SKILL.md/agent-frontmatter shape for
`build_skills_index.py`.

Stdlib only (ADR 0014).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from minimal_yaml import (
    FrontmatterError,
    YamlError,
    extract_frontmatter_block,
    parse_yaml,
)


def skills_for_agent_type(agent_type: str, agents_dir: Path) -> list[str]:
    """Return the `skills:` frontmatter list declared by
    `<agents_dir>/<agent_type>.md`.

    Returns `[]` when the file doesn't exist, has no `skills:` key, or its
    frontmatter can't be parsed — this is a best-effort hint source, never a
    hard dependency, so every failure mode degrades to "no hint" rather than
    raising. Only the one matching agent file is read, never the whole
    `agents_dir`.
    """
    try:
        text = (agents_dir / f"{agent_type}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        frontmatter = parse_yaml(extract_frontmatter_block(text))
    except (FrontmatterError, YamlError):
        return []
    if not isinstance(frontmatter, dict):
        return []
    skills = frontmatter.get("skills")
    if not isinstance(skills, list):
        return []
    return [skill for skill in skills if isinstance(skill, str)]


__all__ = ("skills_for_agent_type",)
