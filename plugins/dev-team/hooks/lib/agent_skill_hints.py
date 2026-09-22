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

import re
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from minimal_yaml import (
    FrontmatterError,
    YamlError,
    extract_frontmatter_block,
    parse_yaml,
)

#: `agent_type` ultimately comes from an Agent/Task dispatch's own
#: `subagent_type` (a PreToolUse hook payload field) — model-controlled
#: input, not a trusted registry lookup. A real agent stem is always a bare
#: identifier (`[A-Za-z0-9_-]+`), so anything else (path separators, `..`,
#: an absolute path) is rejected before it ever reaches the filesystem,
#: rather than relying on `.md`-suffix / read-only / best-effort framing to
#: make a traversal harmless.
_VALID_AGENT_STEM_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def skills_for_agent_type(agent_type: str, agents_dir: Path) -> list[str]:
    """Return the `skills:` frontmatter list declared by
    `<agents_dir>/<agent_type>.md`.

    Returns `[]` when `agent_type` isn't a bare agent-name stem, the file
    doesn't exist, has no `skills:` key, or its frontmatter can't be parsed
    — this is a best-effort hint source, never a hard dependency, so every
    failure mode degrades to "no hint" rather than raising. Only the one
    matching agent file is read, never the whole `agents_dir`.
    """
    if not _VALID_AGENT_STEM_RE.match(agent_type):
        return []
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
