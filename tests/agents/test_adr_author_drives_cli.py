"""Issue #837: the adr-author agent must be able to drive the adr-tools CLI
rather than hand-rolling ADR mechanics.

With an explicit `tools:` allowlist in frontmatter, only listed tools are
available to the agent. The old declaration `tools: Read, Write, Glob, Grep`
gave the agent neither `Bash` (to run the `adr` CLI) nor `Skill` (to load the
`adr-tools` skill that owns the CLI mechanics), so it hand-rolled sequential
numbering, a duplicated ADR template block, and manual index maintenance.

This content guard asserts, over `plugins/dev-team/agents/adr-author.md`:
  (a) frontmatter `tools:` contains both `Bash` and `Skill`;
  (b) the body references the `adr-tools` skill (delegating the mechanics);
  (c) the body no longer hand-rolls numbering ("highest existing number")
      nor carries an embedded `## ADR Template` heading.

Frontmatter parsing mirrors tests/agents/test_agent_effort_frontmatter.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_AUTHOR = REPO_ROOT / "plugins" / "dev-team" / "agents" / "adr-author.md"


def _tools_list(agent_file: Path) -> List[str]:
    """Extract the comma-separated `tools:` list from the leading YAML
    frontmatter block only (between the first two `---` fences). Returns the
    bare tool names, or [] if the key is absent."""
    lines = agent_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return []
    for line in lines[1:]:
        if line == "---":
            break
        match = re.match(r"^\s*tools\s*:\s*(.*)$", line)
        if match:
            value = re.sub(r"\s*#.*$", "", match.group(1)).strip()
            return [t.strip() for t in value.split(",") if t.strip()]
    return []


def _body(agent_file: Path) -> str:
    """Return the agent body (everything after the closing `---` fence)."""
    text = agent_file.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    return parts[2] if len(parts) == 3 else text


def test_adr_author_tools_include_bash_and_skill() -> None:
    tools = _tools_list(ADR_AUTHOR)
    missing = [t for t in ("Bash", "Skill") if t not in tools]
    assert not missing, (
        "adr-author must declare Bash (to run the `adr` CLI) and Skill (to "
        f"load the adr-tools skill) in its tools; missing: {missing}. "
        f"Declared tools: {tools}"
    )


def test_adr_author_references_adr_tools_skill() -> None:
    body = _body(ADR_AUTHOR)
    assert "adr-tools" in body, (
        "adr-author body must reference the adr-tools skill so it delegates "
        "CLI mechanics (numbering, supersede links, TOC) instead of "
        "hand-rolling them."
    )


def test_adr_author_no_hand_rolled_mechanics() -> None:
    body = _body(ADR_AUTHOR)
    assert "highest existing number" not in body, (
        "adr-author must not hand-roll sequential numbering — `adr new` "
        "assigns numbers."
    )
    assert not re.search(r"^##\s+ADR Template\s*$", body, re.MULTILINE), (
        "adr-author must not embed a `## ADR Template` block — `adr new` "
        "emits the template."
    )
