#!/usr/bin/env python3
"""Validate that every review agent declares a scope: frontmatter field.

Exit 0 if all review agents have a scope: field.
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


def parse_frontmatter(text: str) -> dict:
    """Return a dict of simple key: value pairs from YAML frontmatter.

    Handles both scalar values (key: value) and list values:
        key:
          - item1
          - item2
    Returns {} if there is no frontmatter block.
    """
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    fm_text = text[3:end]
    result: dict = {}
    current_key = None
    for line in fm_text.splitlines():
        # List item continuation
        stripped = line.strip()
        if stripped.startswith("- ") and current_key is not None:
            value = stripped[2:].strip()
            if isinstance(result.get(current_key), list):
                result[current_key].append(value)
            else:
                result[current_key] = [value]
            continue
        # Key: value pair
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            current_key = m.group(1)
            val = m.group(2).strip()
            if val:
                result[current_key] = val
            else:
                result[current_key] = []  # will be populated by list items
        else:
            current_key = None
    return result


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
        fm = parse_frontmatter(text)
        if not fm:
            # No frontmatter — skip (not an agent file)
            continue
        if "scope" not in fm:
            missing.append(name)

    if missing:
        print("FAIL: the following review agents are missing a 'scope:' frontmatter field:")
        for name in missing:
            print(f"  - {name}")
        print(
            "\nAdd 'scope: always' for language-agnostic agents, or a list of glob patterns "
            "for file-type-scoped agents.  See plugins/dev-team/docs/developer-notes.md."
        )
        return 1

    print(f"OK: all {len(list(agents_dir.glob('*.md'))) - len(NON_REVIEW_AGENTS)} "
          f"review agents declare a scope: field.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
