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
the 8 agents that reason about arbitrary target-repo code, as opposed to
the 5 synthesis-only agents (`redteam-report-generator`,
`exec-report-generator`, `redteam-recon-analyzer`,
`redteam-evasion-analyzer`, `redteam-extraction-analyzer`) that only ever
read a fixed set of upstream probe/finding artifacts and produce narrative
output — the grant would be inert for them. This classification (not a
`Glob`-presence heuristic — `exec-report-generator` carries `Glob` for its
own artifact-directory walk yet is still synthesis-only) is the one
actually applied to the fleet.

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
    run_grants_check,
)

# The security-assessment code-reading agents (#1388) — the 8 agents that
# reason about arbitrary target-repo code. Named explicitly (not a glob
# pattern, not a tools:-heuristic) so a newly added agent must be classified
# here or in NON_CODE_READING_AGENTS rather than silently landing in either
# bucket.
CODE_READING_AGENTS = [
    "authorization-logic-review",
    "business-logic-domain-review",
    "compliance-edge-annotator",
    "cross-repo-synthesizer",
    "deep-code-reasoning",
    "fp-reduction",
    "recon-driven-scan",
    "tool-finding-narrative-annotator",
]

# Documented exclusions: the 5 synthesis-only security-assessment agents —
# they interpret a fixed set of upstream artifacts (redteam probe output,
# prior-phase findings) and produce narrative/report output, never reasoning
# about arbitrary target-repo code, so the code-intelligence grant would be
# inert for them. `exec-report-generator` carries `Glob` (for its own
# artifact-directory walk) but is still synthesis-only — Glob presence alone
# is not the classifying signal.
NON_CODE_READING_AGENTS = [
    "exec-report-generator",
    "redteam-evasion-analyzer",
    "redteam-extraction-analyzer",
    "redteam-recon-analyzer",
    "redteam-report-generator",
]


def _agents_dir_default() -> Path:
    # scripts/ is one level below plugins/dev-team/; the companion plugin is a
    # sibling of dev-team under plugins/.
    return Path(__file__).parent.parent.parent / "security-assessment" / "agents"


def _targets(agents_dir: Path) -> dict[str, tuple[Path, list[str]]]:
    return {
        name: (agents_dir / f"{name}.md", BASE_MCP_TOOLS) for name in CODE_READING_AGENTS
    }


def find_offenders(agents_dir: Path) -> dict[str, list[str]]:
    """Return {agent: missing tool names} for code-reading agents under-granted."""
    offenders, _fixed, _unfixable = run_grants_check(_targets(agents_dir))
    return offenders


def unclassified_agents(agents_dir: Path) -> list[str]:
    """Agents on disk that are in neither roster — the self-extension net."""
    known = set(CODE_READING_AGENTS) | set(NON_CODE_READING_AGENTS)
    return sorted(
        path.stem for path in agents_dir.glob("*.md") if path.stem not in known
    )


def apply_fixes(agents_dir: Path) -> dict[str, list[str]]:
    """Append missing BASE_MCP_TOOLS to each under-granted code-reading agent."""
    _offenders, fixed, _unfixable = run_grants_check(_targets(agents_dir), apply_fix=True)
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

    offenders, fixed, _unfixable = run_grants_check(_targets(agents_dir), apply_fix=args.fix)
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
