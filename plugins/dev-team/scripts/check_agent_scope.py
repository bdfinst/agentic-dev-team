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

# Keeps PEP 585 annotations (`list[str]`) as strings, so this module imports on
# the floor ADR 0014 sets for shipped code.
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
# The `agents/` directory root is the shared, resolved single source of
# truth in hooks/lib (#1904 item 3) — scripts/ -> hooks/lib/ is the correct
# dependency direction (see review_agent_registry.py's own docstring). This
# script globs all agents/*.md (not just *-review.md), so it uses only
# default_agents_dir() for the directory path — never
# registered_review_agent_names()/find_review_agent_files(), which are
# review-agent-specific.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "lib"))

# Review agents are the agents named in the Review Agents section of
# knowledge/agent-registry.md.  Rather than parsing that file we check all
# agents/*.md files that contain a 'description:' frontmatter field and are
# not one of the well-known non-review agents.  The exclusion set is shared
# with select_lenses.py (#1516) — see scripts/lib/review_roster.py.
from review_agent_registry import default_agents_dir
from review_roster import NON_REVIEW_AGENTS
from review_roster import SCOPE_LINE_RE as SCOPE_RE


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
        agents_dir = default_agents_dir()

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
            "\nAdd one of: 'Scope: always' (language-agnostic, every diff), a bullet list "
            "of glob patterns (file-type-scoped), 'Scope: added-only' + globs (only newly-"
            "added matching files), or 'Scope: on-demand' (never per-diff — dispatched by "
            "name or by /repo-review).  See plugins/dev-team/docs/developer-notes.md."
        )
        return 1

    print(f"OK: all {len(list(agents_dir.glob('*.md'))) - len(NON_REVIEW_AGENTS)} "
          f"review agents declare a Scope: field.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
