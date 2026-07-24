#!/usr/bin/env python3
"""Validate security-assessment code-reading agents' code-intelligence MCP grants.

`check_review_agent_mcp_tools.py` (#1102) enforces the canonical CodeGraph/
Repowise grant (`mcp_tool_grants.BASE_MCP_TOOLS`) on dev-team's own read-only
`*-review.md` agents, but is scoped to `plugins/dev-team/agents/` only — it
never sees `plugins/security-assessment/agents/`. That companion plugin's
code-reading agents were hand-granted the same canonical set (hand-copied
from `plugins/dev-team/agents/security-review.md`), and a hand-maintained
grant with no mechanical check silently drifts the moment `BASE_MCP_TOOLS`
changes (issue #1388).

Unlike the dev-team review agents (uniformly named `*-review.md`), the
security-assessment agents this applies to don't share a filename
convention, so — mirroring `check_agent_tool_mapping.py`'s named-target
approach rather than a glob — this script validates an explicit roster:
the agents whose `tools:` frontmatter already includes `Glob` (broad
codebase/artifact-tree traversal, the same file-discovery capability every
dev-team `*-review.md` agent carries), as opposed to the narrower
probe-interpretation/report-narrative agents that only ever read a fixed
set of upstream JSON artifacts via `Read`/`Grep`.

Usage:
    python3 check_security_assessment_mcp_tools.py [--agents-dir <path>]
    python3 check_security_assessment_mcp_tools.py --fix     # append missing tools
    python3 check_security_assessment_mcp_tools.py --json     # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from mcp_tool_grants import (
    BASE_MCP_TOOLS,
    fix_tools_line,
    missing_tools,
    parse_tools,
)

# The security-assessment code-reading agents (#1388) — every agent in
# plugins/security-assessment/agents/ whose tools: line grants Glob, i.e.
# does broad codebase/artifact-tree traversal rather than reading a fixed
# set of upstream probe/report artifacts. Named explicitly (not a glob
# pattern) so a newly added agent must be classified here or in
# NON_CODE_READING_AGENTS rather than silently landing in either bucket.
CODE_READING_AGENTS = [
    "authorization-logic-review",
    "business-logic-domain-review",
    "cross-repo-synthesizer",
    "deep-code-reasoning",
    "exec-report-generator",
    "fp-reduction",
    "recon-driven-scan",
    "tool-finding-narrative-annotator",
]

# Documented exclusions: security-assessment agents that interpret a fixed
# set of upstream artifacts (redteam probe output, prior-phase findings) via
# Read/Grep only — no Glob, no broad codebase traversal — so the
# code-intelligence grant would be inert for them.
NON_CODE_READING_AGENTS = [
    "compliance-edge-annotator",
    "redteam-evasion-analyzer",
    "redteam-extraction-analyzer",
    "redteam-recon-analyzer",
    "redteam-report-generator",
]


def _agents_dir_default() -> Path:
    # scripts/ is one level below plugins/dev-team/; the companion plugin is a
    # sibling of dev-team under plugins/.
    return Path(__file__).parent.parent.parent / "security-assessment" / "agents"


def find_offenders(agents_dir: Path) -> dict[str, list[str]]:
    """Return {agent: missing tool names} for code-reading agents under-granted."""
    offenders: dict[str, list[str]] = {}
    for name in CODE_READING_AGENTS:
        path = agents_dir / f"{name}.md"
        if not path.is_file():
            offenders[name] = list(BASE_MCP_TOOLS)  # named target missing
            continue
        missing = missing_tools(path.read_text(encoding="utf-8"), BASE_MCP_TOOLS)
        if missing:
            offenders[name] = missing
    return offenders


def unclassified_agents(agents_dir: Path) -> list[str]:
    """Agents on disk that are in neither roster — the self-extension net."""
    known = set(CODE_READING_AGENTS) | set(NON_CODE_READING_AGENTS)
    return sorted(
        path.stem for path in agents_dir.glob("*.md") if path.stem not in known
    )


def apply_fixes(agents_dir: Path) -> dict[str, list[str]]:
    """Append missing BASE_MCP_TOOLS to each under-granted code-reading agent."""
    fixed: dict[str, list[str]] = {}
    for name in CODE_READING_AGENTS:
        path = agents_dir / f"{name}.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if parse_tools(text) is None:
            continue
        new_text, added = fix_tools_line(text, BASE_MCP_TOOLS)
        if added:
            path.write_text(new_text, encoding="utf-8")
            fixed[name] = added
    return fixed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents-dir", type=Path, default=None)
    parser.add_argument("--fix", action="store_true", help="append missing MCP tool names")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    agents_dir = args.agents_dir or _agents_dir_default()
    if not agents_dir.is_dir():
        print(f"ERROR: agents directory not found: {agents_dir}", file=sys.stderr)
        return 1

    if args.fix:
        fixed = apply_fixes(agents_dir)

    offenders = find_offenders(agents_dir)
    unclassified = unclassified_agents(agents_dir)
    rc = 1 if (offenders or unclassified) else 0

    if args.json:
        out = {
            "reviewed": list(CODE_READING_AGENTS),
            "offenders": offenders,
            "unclassified": unclassified,
        }
        if args.fix:
            out["fixed"] = fixed
        print(json.dumps(out, indent=2))
        return rc

    if args.fix:
        if fixed:
            for name, added in fixed.items():
                print(f"FIXED: {name} — added {', '.join(added)}")
        else:
            print("OK: all security-assessment code-reading agents already grant the MCP tools.")

    if offenders:
        print("FAIL: security-assessment code-reading agents missing code-intelligence MCP tools:")
        for name, missing in offenders.items():
            print(f"  - {name}: missing {', '.join(missing)}")
        print("\nRun: python3 plugins/dev-team/scripts/check_security_assessment_mcp_tools.py --fix")
    if unclassified:
        print("FAIL: security-assessment agents in neither CODE_READING_AGENTS nor "
              "NON_CODE_READING_AGENTS (classify each):")
        for name in unclassified:
            print(f"  - {name}")
    if rc == 0:
        print(f"OK: all {len(CODE_READING_AGENTS)} security-assessment code-reading agents "
              "grant the five MCP tools.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
