#!/usr/bin/env python3
"""Validate per-agent-tier MCP tool grants on every read-only *-review agent.

Review agents (agents/*-review.md) do structural and behavioral review. When a
target repo has a CodeGraph index (.codegraph/) and/or a Repowise MCP server, the
agents should call those tools for verified skeletons and resolved call graphs
instead of re-reading whole files. That only works if the tool names are present
in each agent's `tools:` frontmatter allowlist.

Grants are no longer one-size-fits-all (#1467). Three tiers:

- ``EXEMPT_AGENTS`` (``claude-setup-review``, ``token-efficiency-review``) — pure
  text/regex/frontmatter validators on the ``haiku`` tier that never touch code
  structure. They require **none** of the code-intelligence MCP tools, and this
  check actively asserts they carry **none** of them — a "forbidden tools
  present" failure mode, reported and JSON-exposed distinctly from the ordinary
  "missing tools" offenders, so a future edit can't silently regrant the tools
  these two never needed.
- ``REASSIGNED_TOOLS`` agents (``refactor-opportunity-review``,
  ``performance-review``, ``complexity-review``, ``doc-review``) — require their
  own specific tool set (see the mapping below) instead of the generic
  ``BASE_MCP_TOOLS`` five.
- Every other ``*-review.md`` agent keeps the original ``BASE_MCP_TOOLS``
  requirement, unchanged.

``--fix`` behavior: for ``REASSIGNED_TOOLS`` (and generic-tier) agents, it
appends the agent's own missing required tools (reusing
``run_grants_check``/``fix_tools_line`` from ``mcp_tool_grants.py``, which are
generic over the ``required`` list). For ``EXEMPT_AGENTS``, ``--fix`` is a
no-op for "missing" (there is nothing required). **`--fix` does NOT strip
forbidden tools from exempt agents** — removing an already-present token is a
different, riskier operation than appending one, so a forbidden-tools finding
on an exempt agent always requires a human edit; detection still fails the run
so it can't be missed.

Exit 0 if every review agent's grant matches its tier and the skill prose is
present. Exit 1 (detection) or applies fixes (--fix) otherwise.

Usage:
    python3 check_review_agent_mcp_tools.py [--agents-dir <path>] [--skill-file <path>]
    python3 check_review_agent_mcp_tools.py --fix        # append missing tool names
    python3 check_review_agent_mcp_tools.py --json        # machine-readable report
"""

# Keeps PEP 585 annotations (`list[Path]`, `dict[str, list[str]]`) as strings,
# so this module imports on the floor ADR 0014 sets for shipped.
# code. Without it this file raised `TypeError: 'type' object is not
# subscriptable` at import time.
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Shared tool-name constants and tools:-line plumbing live in scripts/lib so the
# sibling check_agent_tool_mapping.py can import them as a peer (neither script is
# the other's library). See scripts/lib/mcp_tool_grants.py.
sys.path.insert(0, str(Path(__file__).parent / "lib"))
# The *-review glob-discovery logic itself lives in hooks/lib (#1461) — a
# hook (hooks/agent_dispatch_ledger.py) needs the same closed set of
# registered review-agent names and must never reach into scripts/, so the
# dependency direction is scripts/ -> hooks/lib/, not the reverse. This
# script imports the shared implementation rather than keeping its own copy.
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "lib"))

from mcp_tool_grants import (
    BASE_MCP_TOOLS,
    GET_DEAD_CODE,
    GET_HEALTH,
    GET_WHY,
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
from review_agent_registry import (
    find_review_agent_files as _find_review_agent_files,
)

# The five code-intelligence MCP tool names granted to the generic review-agent
# tier. Kept as MCP_TOOL_NAMES for this script's public API (imported by the
# pytest wrapper and agent-audit); the canonical values live in the shared lib.
MCP_TOOL_NAMES = BASE_MCP_TOOLS

# Agents that do pure text/regex/frontmatter validation and never touch code
# structure — they require zero code-intelligence MCP tools (#1467).
EXEMPT_AGENTS = {"claude-setup-review", "token-efficiency-review"}

# Agents whose grant is reassigned to a specific set instead of the generic
# BASE_MCP_TOOLS five (#1467).
REASSIGNED_TOOLS = {
    "refactor-opportunity-review": [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        GET_DEAD_CODE,
        GET_HEALTH,
    ],
    "performance-review": [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__search_codebase",
        GET_HEALTH,
    ],
    "complexity-review": [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        "mcp__plugin_repowise_repowise__search_codebase",
        GET_HEALTH,
    ],
    "doc-review": [
        "mcp__codegraph__codegraph_explore",
        "mcp__plugin_repowise_repowise__get_context",
        "mcp__plugin_repowise_repowise__get_symbol",
        GET_WHY,
    ],
}

# Every code-intelligence MCP tool name that must be ABSENT from an
# EXEMPT_AGENTS agent's tools: line.
FORBIDDEN_FOR_EXEMPT = BASE_MCP_TOOLS + [GET_WHY, GET_HEALTH, GET_DEAD_CODE]

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
    """Return the read-only review agent files (agents/*-review.md), sorted.

    Thin wrapper over the shared `hooks/lib/review_agent_registry` extraction
    (#1461) — kept as a stable public name here since this script's own
    tests and `hooks/agent_dispatch_ledger.py`'s registry needs both depend
    on this glob-discovery behavior remaining unchanged.
    """
    return _find_review_agent_files(agents_dir)


def required_tools_for(name: str) -> list[str]:
    """Return the tool-name list a review agent named `name` must grant.

    Empty for EXEMPT_AGENTS, the agent's own set for REASSIGNED_TOOLS, and
    the generic BASE_MCP_TOOLS five for every other *-review agent.
    """
    if name in EXEMPT_AGENTS:
        return []
    if name in REASSIGNED_TOOLS:
        return REASSIGNED_TOOLS[name]
    return MCP_TOOL_NAMES


def missing_mcp_tools(text: str, name: str) -> list[str]:
    """Return the tool names required for agent `name` absent from its tools: line."""
    return _missing_tools(text, required_tools_for(name))


def fix_tools_line(text: str, name: str) -> tuple[str, list[str]]:
    """Append any missing required tool names for agent `name`. Idempotent.

    Thin wrapper over the shared helper, bound to `name`'s required set via
    `required_tools_for`. Returns (new_text, added_names); a line already
    containing every required name is returned unchanged (added == []). For
    an EXEMPT_AGENTS name (required == []), always returns unchanged.
    """
    return _fix_tools_line(text, required_tools_for(name))


def forbidden_present(text: str) -> list[str]:
    """Return the FORBIDDEN_FOR_EXEMPT tool names actually granted in `text`."""
    missing = _missing_tools(text, FORBIDDEN_FOR_EXEMPT)
    return [name for name in FORBIDDEN_FOR_EXEMPT if name not in missing]


def check_skill(skill_text: str) -> list[str]:
    """Return the required phrases absent from the code-review skill prose."""
    return [phrase for phrase in SKILL_REQUIRED_PHRASES if phrase not in skill_text]


def _skill_missing(skill_file: Path) -> list[str]:
    if skill_file.is_file():
        return check_skill(skill_file.read_text(encoding="utf-8"))
    return list(SKILL_REQUIRED_PHRASES)


def _targets(agents: list[Path]) -> dict[str, tuple[Path, list[str]]]:
    return {agent_file.stem: (agent_file, required_tools_for(agent_file.stem)) for agent_file in agents}


def apply_fixes(agents: list[Path]) -> tuple[dict[str, list[str]], list[str]]:
    """Append missing required tools to each review agent. Returns (fixed, unfixable).

    `unfixable` names agents with no inline `tools:` line the regex can append
    to (a missing line, or a block-list form) — these are reported and cause a
    non-zero exit rather than a silent false "OK" (they can't be auto-fixed).
    Never strips forbidden tools from EXEMPT_AGENTS — see module docstring.
    """
    _offenders, fixed, unfixable = run_grants_check(_targets(agents), apply_fix=True)
    return fixed, unfixable


def find_offenders(agents: list[Path]) -> dict[str, list[str]]:
    """Return {agent: missing tool names} for review agents lacking their required set."""
    offenders, _fixed, _unfixable = run_grants_check(_targets(agents))
    return offenders


def find_forbidden(agents: list[Path]) -> dict[str, list[str]]:
    """Return {agent: [forbidden tool names present]} for EXEMPT_AGENTS only."""
    forbidden = {}
    for agent_file in agents:
        if agent_file.stem not in EXEMPT_AGENTS or not agent_file.is_file():
            continue
        present = forbidden_present(agent_file.read_text(encoding="utf-8"))
        if present:
            forbidden[agent_file.stem] = present
    return forbidden


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents-dir", type=Path, default=None)
    parser.add_argument("--skill-file", type=Path, default=None)
    parser.add_argument("--fix", action="store_true", help="append missing required tool names")
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
    forbidden = find_forbidden(agents)

    if args.fix:
        rc = 1 if (unfixable or skill_missing or forbidden) else 0
        if args.json:
            # --json owns stdout: emit ONLY the JSON object, nothing else.
            report = build_json_report(
                "review-agent-mcp-tools",
                [a.stem for a in agents],
                offenders,
                ok=(rc == 0),
                fixed=fixed,
                unfixable=unfixable,
                notes={"skill_missing_phrases": skill_missing, "forbidden": forbidden},
            )
            print(json.dumps(report, indent=2))
            return rc
        if fixed:
            for name, added in fixed.items():
                print(f"FIXED: {name} — added {', '.join(added)}")
        else:
            print(f"OK: all {len(agents)} review agents already grant their required MCP tools.")
        if unfixable:
            print("WARN: review agents with no inline tools: line (fix by hand): "
                  + ", ".join(unfixable), file=sys.stderr)
        if skill_missing:
            print("WARN: code-review SKILL.md is missing phrases (fix by hand): "
                  + ", ".join(skill_missing), file=sys.stderr)
        if forbidden:
            print("WARN: exempt review agents granted forbidden MCP tools (fix by hand): "
                  + "; ".join(f"{name}: {', '.join(tools)}" for name, tools in forbidden.items()),
                  file=sys.stderr)
        return rc

    rc = 1 if (offenders or skill_missing or forbidden) else 0
    if args.json:
        # --json owns stdout: emit ONLY the JSON object, nothing else.
        report = build_json_report(
            "review-agent-mcp-tools",
            [a.stem for a in agents],
            offenders,
            ok=(rc == 0),
            notes={"skill_missing_phrases": skill_missing, "forbidden": forbidden},
        )
        print(json.dumps(report, indent=2))
        return rc
    if offenders:
        print("FAIL: review agents missing their required code-intelligence MCP tools in tools::")
        for name, missing in offenders.items():
            print(f"  - {name}: missing {', '.join(missing)}")
        print("\nRun: python3 scripts/check_review_agent_mcp_tools.py --fix")
    if forbidden:
        print("FAIL: exempt review agents granted forbidden code-intelligence MCP tools (should have none):")
        for name, tools in forbidden.items():
            print(f"  - {name}: forbidden {', '.join(tools)}")
    if skill_missing:
        print("FAIL: code-review SKILL.md missing required phrases: " + ", ".join(skill_missing))
    if rc == 0:
        print(f"OK: all {len(agents)} review agents grant their required MCP tools; skill prose present.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
