#!/usr/bin/env python3
"""Validate that every review agent declares a body-level Scope: field.

``Scope:`` is a body-level declaration, not frontmatter (issue #1333 — it is
not part of the official Claude Code sub-agent contract; see
plugins/marketplace-dev/knowledge/agent-contract.json).

Exit 0 if all review agents have a Scope: line in their body.
Exit 1 with a list of offending agents if any are missing.

Usage:
    python3 check_agent_scope.py [--agents-dir <path>]

The agents directory defaults to plugins/dev-team/agents/ relative to the
repo root (inferred from this script's location).
"""

import argparse
import re
import sys
from pathlib import Path

# Review agents are the agents named in the Review Agents section of
# knowledge/agent-registry.md.  Rather than parsing that file we check all
# agents/*.md files that contain a 'description:' frontmatter field and are
# not one of the well-known non-review agents.
NON_REVIEW_AGENTS = {
    "adr-author",
    "architect",
    "codebase-recon",
    "data-flow-tracer",
    "mutation-kill",
    "orchestrator",
    "platform-engineer",
    "product-manager",
    "progress-guardian",
    "qa-engineer",
    "security-engineer",
    "session-analysis",
    "software-engineer",
    "tech-writer",
    "ui-ux-designer",
}

SCOPE_RE = re.compile(r"^\s*Scope\s*:\s*(.*)$")


def has_frontmatter(text: str) -> bool:
    """True if the file opens with a YAML frontmatter block."""
    return text.startswith("---") and "---" in text[3:]


def strip_frontmatter(text: str) -> str:
    """Return the body (everything after the frontmatter block)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    after = text.find("\n", end + 1)
    return text[after + 1:] if after != -1 else ""


def declares_scope(body: str) -> bool:
    """True if the body contains a Scope: line (scalar or block-list)."""
    return any(SCOPE_RE.match(line) for line in body.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agents-dir",
        type=Path,
        default=None,
        help="Path to the agents/ directory (default: auto-detect from script location)",
    )
    args = parser.parse_args()

    if args.agents_dir is not None:
        agents_dir = args.agents_dir
    else:
        # scripts/ is one level below plugins/dev-team/
        agents_dir = Path(__file__).parent.parent / "agents"

    if not agents_dir.is_dir():
        print(f"ERROR: agents directory not found: {agents_dir}", file=sys.stderr)
        return 1

    missing: list[str] = []
    for agent_file in sorted(agents_dir.glob("*.md")):
        name = agent_file.stem
        if name in NON_REVIEW_AGENTS:
            continue
        text = agent_file.read_text(encoding="utf-8")
        if not has_frontmatter(text):
            # No frontmatter — skip (not an agent file)
            continue
        body = strip_frontmatter(text)
        if not declares_scope(body):
            missing.append(name)

    if missing:
        print("FAIL: the following review agents are missing a 'Scope:' body declaration:")
        for name in missing:
            print(f"  - {name}")
        print(
            "\nAdd 'Scope: always' for language-agnostic agents, or a list of glob patterns "
            "for file-type-scoped agents.  See plugins/dev-team/docs/developer-notes.md."
        )
        return 1

    print(f"OK: all {len(list(agents_dir.glob('*.md'))) - len(NON_REVIEW_AGENTS)} "
          f"review agents declare a Scope: field.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
