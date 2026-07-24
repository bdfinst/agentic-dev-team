#!/usr/bin/env python3
"""Validate that every read-only *-review agent grants the code-intelligence MCP tools.

Review agents (agents/*-review.md) do structural and behavioral review. When a
target repo has a CodeGraph index (.codegraph/) and/or a Repowise MCP server, the
agents should call those tools for verified skeletons and resolved call graphs
instead of re-reading whole files. That only works if the tool names are present
in each agent's `tools:` frontmatter allowlist. This check enforces that, and
--fix appends any missing names (merge, never replace — Read/Grep/Glob/Skill are
preserved). A granted tool whose MCP server is absent is simply unavailable at
runtime (no error); agents fall back to Read/Grep/Glob.

It also verifies the code-review skill documents detecting the index and
preferring it over full-file reads (the guidance that makes the grant useful).

Exit 0 if every review agent grants all five tools and the skill prose is present.
Exit 1 (detection) or applies fixes (--fix) otherwise.

Usage:
    python3 check_review_agent_mcp_tools.py [--agents-dir <path>] [--skill-file <path>]
    python3 check_review_agent_mcp_tools.py --fix        # append missing tool names
    python3 check_review_agent_mcp_tools.py --json        # machine-readable report
"""

import argparse
import json
import sys
from pathlib import Path

# Shared tool-name constants and tools:-line plumbing live in scripts/lib so the
# sibling check_agent_tool_mapping.py can import them as a peer (neither script is
# the other's library). See scripts/lib/mcp_tool_grants.py.
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from mcp_tool_grants import (
    BASE_MCP_TOOLS,
    build_json_report,
    parse_tools,  # noqa: F401 -- re-exported: imported directly by this script's own tests
    run_grants_check,
)
from mcp_tool_grants import (
    fix_tools_line as _fix_tools_line,
)
from mcp_tool_grants import (
    missing_tools as _missing_tools,
)

# The five code-intelligence MCP tool names granted to read-only review agents.
# Kept as MCP_TOOL_NAMES for this script's public API (imported by the pytest
# wrapper and agent-audit); the canonical values live in the shared lib.
MCP_TOOL_NAMES = BASE_MCP_TOOLS

# Phrases the code-review skill must contain so the granted tools are actually used:
# detection of each index, the preference instruction, and the documented fallback.
SKILL_REQUIRED_PHRASES = [
    "mcp__codegraph__codegraph_explore",
    ".codegraph/",
    "get_context",
    "get_symbol",
    "search_codebase",
    "get_risk",
]


def _agents_dir_default() -> Path:
    # scripts/ is one level below plugins/dev-team/
    return Path(__file__).parent.parent / "agents"


def _skill_file_default() -> Path:
    return Path(__file__).parent.parent / "skills" / "code-review" / "SKILL.md"


def find_review_agents(agents_dir: Path) -> list[Path]:
    """Return the read-only review agent files (agents/*-review.md), sorted."""
    return sorted(agents_dir.glob("*-review.md"))


def missing_mcp_tools(text: str) -> list[str]:
    """Return the MCP tool names absent from the agent's tools: line (all five if no line)."""
    return _missing_tools(text, MCP_TOOL_NAMES)


def fix_tools_line(text: str) -> tuple[str, list[str]]:
    """Append any missing MCP tool names to the tools: line. Idempotent.

    Thin wrapper over the shared helper, bound to this script's MCP_TOOL_NAMES.
    Returns (new_text, added_names); a line already containing all five is
    returned unchanged (added == []).
    """
    return _fix_tools_line(text, MCP_TOOL_NAMES)


def check_skill(skill_text: str) -> list[str]:
    """Return the required phrases absent from the code-review skill prose."""
    return [phrase for phrase in SKILL_REQUIRED_PHRASES if phrase not in skill_text]


def _skill_missing(skill_file: Path) -> list[str]:
    if skill_file.is_file():
        return check_skill(skill_file.read_text(encoding="utf-8"))
    return list(SKILL_REQUIRED_PHRASES)


def _targets(agents: list[Path]) -> dict[str, tuple[Path, list[str]]]:
    return {agent_file.stem: (agent_file, MCP_TOOL_NAMES) for agent_file in agents}


def apply_fixes(agents: list[Path]) -> tuple[dict[str, list[str]], list[str]]:
    """Append missing MCP tools to each review agent. Returns (fixed, unfixable).

    `unfixable` names agents with no inline `tools:` line the regex can append
    to (a missing line, or a block-list form) — these are reported and cause a
    non-zero exit rather than a silent false "OK" (they can't be auto-fixed).
    """
    _offenders, fixed, unfixable = run_grants_check(_targets(agents), apply_fix=True)
    return fixed, unfixable


def find_offenders(agents: list[Path]) -> dict[str, list[str]]:
    """Return {agent: missing tool names} for review agents lacking any of the five."""
    offenders, _fixed, _unfixable = run_grants_check(_targets(agents))
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents-dir", type=Path, default=None)
    parser.add_argument("--skill-file", type=Path, default=None)
    parser.add_argument("--fix", action="store_true", help="append missing MCP tool names")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    agents_dir = args.agents_dir or _agents_dir_default()
    skill_file = args.skill_file or _skill_file_default()

    if not agents_dir.is_dir():
        print(f"ERROR: agents directory not found: {agents_dir}", file=sys.stderr)
        return 1

    agents = find_review_agents(agents_dir)
    skill_missing = _skill_missing(skill_file)
    offenders, fixed, unfixable = run_grants_check(_targets(agents), apply_fix=args.fix)

    if args.fix:
        rc = 1 if (unfixable or skill_missing) else 0
        if args.json:
            # --json owns stdout: emit ONLY the JSON object, nothing else.
            report = build_json_report(
                "review-agent-mcp-tools",
                [a.stem for a in agents],
                offenders,
                ok=(rc == 0),
                fixed=fixed,
                unfixable=unfixable,
                notes={"skill_missing_phrases": skill_missing},
            )
            print(json.dumps(report, indent=2))
            return rc
        if fixed:
            for name, added in fixed.items():
                print(f"FIXED: {name} — added {', '.join(added)}")
        else:
            print(f"OK: all {len(agents)} review agents already grant the MCP tools.")
        if unfixable:
            print("WARN: review agents with no inline tools: line (fix by hand): "
                  + ", ".join(unfixable), file=sys.stderr)
        if skill_missing:
            print("WARN: code-review SKILL.md is missing phrases (fix by hand): "
                  + ", ".join(skill_missing), file=sys.stderr)
        return rc

    rc = 1 if (offenders or skill_missing) else 0
    if args.json:
        # --json owns stdout: emit ONLY the JSON object, nothing else.
        report = build_json_report(
            "review-agent-mcp-tools",
            [a.stem for a in agents],
            offenders,
            ok=(rc == 0),
            notes={"skill_missing_phrases": skill_missing},
        )
        print(json.dumps(report, indent=2))
        return rc
    if offenders:
        print("FAIL: review agents missing code-intelligence MCP tools in tools::")
        for name, missing in offenders.items():
            print(f"  - {name}: missing {', '.join(missing)}")
        print("\nRun: python3 scripts/check_review_agent_mcp_tools.py --fix")
    if skill_missing:
        print("FAIL: code-review SKILL.md missing required phrases: " + ", ".join(skill_missing))
    if rc == 0:
        print(f"OK: all {len(agents)} review agents grant the five MCP tools; skill prose present.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
