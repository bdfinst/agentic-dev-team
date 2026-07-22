"""Shared plugin agent-directory constant and frontmatter helpers for
fleet-wide frontmatter gates (color:, and future conventions after it).

A superset of `test_agent_effort_frontmatter.py`'s own two-dir `AGENTS_DIRS`
(dev-team, security-assessment) — that file's list stays as-is deliberately,
so extending it here doesn't retroactively subject `marketplace-dev`'s one
agent to its unrelated existing checks (effort-band values, description
colon, context-needs) as a side effect. Fleet-wide conventions introduced
after `color:`/`skills:`/`memory:` (#1334/#1335) that should cover
`marketplace-dev` from day one import this module instead.

`_frontmatter_block`/`_frontmatter_field` are this module's own primitive
(read a file's leading `---`-fenced block, extract one field) -- kept
separate from `test_agent_effort_frontmatter.py`'s differently-shaped
helpers (which read+extract in one call) rather than unifying the two, to
avoid touching that established file's behavior for an unrelated change.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PLUGIN_AGENTS_DIRS = [
    REPO_ROOT / "plugins" / "dev-team" / "agents",
    REPO_ROOT / "plugins" / "security-assessment" / "agents",
    REPO_ROOT / "plugins" / "marketplace-dev" / "agents",
]


def frontmatter_block(agent_file: Path) -> str:
    """Return the leading YAML frontmatter block (between the `---` fences),
    or "" if the file has none."""
    lines = agent_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return ""
    body = []
    for line in lines[1:]:
        if line == "---":
            break
        body.append(line)
    return "\n".join(body)


def frontmatter_field(fm: str, field: str) -> str:
    """Extract one field's value from an already-extracted frontmatter block
    (stripped, unquoted, inline comments removed). Returns "" if absent."""
    match = re.search(rf"^\s*{re.escape(field)}\s*:\s*(.*)$", fm, re.MULTILINE)
    if not match:
        return ""
    value = match.group(1)
    value = re.sub(r"\s*#.*$", "", value)
    return value.strip().strip("\"'").strip()
