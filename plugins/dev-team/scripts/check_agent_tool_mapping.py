#!/usr/bin/env python3
"""Validate the non-review agent→code-intelligence-tool mapping (#1108).

#1102 granted the 24 read-only ``*-review`` agents a fixed MCP tool set
(``check_review_agent_mcp_tools.py``). #1108 extends the grant to the non-review
team agents by **tier**:

- **narrow** — codegraph + the four Repowise tools (``BASE_MCP_TOOLS``):
  ``software-engineer``, ``mutation-kill``, ``qa-engineer``, ``data-flow-tracer``.
  ``data-flow-tracer`` additionally gets a scoped ``Bash(graphify *)`` grant (its
  sole execution capability — it invokes the Graphify CLI for cross-layer traces).
- **rationale** — the narrow set plus ``get_why`` (code-existence rationale):
  ``adr-author``, ``architect``, ``security-engineer``, ``platform-engineer``,
  ``codebase-recon``.

Coverage is the **union** of two branches so a named target is always validated
even when it carries no persona marker, and a *new* team agent can't silently
escape the mapping:

- (a) every agent named in ``TIER_CONFIG`` — deterministic coverage of the known
  targets (``codebase-recon`` is ``Enforcement: script``; ``mutation-kill`` carries
  neither persona marker — branch (b) alone would miss both).
- (b) the structural sweep — team agents detected by a ``## Behavioral Guidelines``
  section *or* an ``Enforcement: script`` body line (not frontmatter — issue
  #1333), minus ``*-review.md``, minus the documented ``EXCLUSIONS``. A swept
  agent in neither ``TIER_CONFIG`` nor ``EXCLUSIONS`` is *unclassified* and
  fails — the self-extension net.

A granted MCP tool whose server is absent is inert at runtime; agents fall back to
Read/Grep/Glob.

Usage (repo-root-relative — this script mutates the agent files next to
wherever it itself resides, so it must run against the maintainer's own
checkout, never a `${CLAUDE_PLUGIN_ROOT}`-qualified installed-cache path):
    python3 plugins/dev-team/scripts/check_agent_tool_mapping.py [--agents-dir <path>]
    python3 plugins/dev-team/scripts/check_agent_tool_mapping.py --fix     # append missing tier tools
    python3 plugins/dev-team/scripts/check_agent_tool_mapping.py --json     # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from mcp_tool_grants import (
    BASE_MCP_TOOLS,
    GET_WHY,
    build_json_report,
    run_grants_check,
)

# Tiers ---------------------------------------------------------------------
NARROW = list(BASE_MCP_TOOLS)
RATIONALE = BASE_MCP_TOOLS + [GET_WHY]
_GRAPHIFY_BASH = "Bash(graphify *)"

# The canonical non-review mapping. Each agent → the tool names its tier requires
# in `tools:` (merge target, never a replacement — existing grants are preserved).
TIER_CONFIG = {
    "software-engineer": NARROW,
    "mutation-kill": NARROW,
    "qa-engineer": NARROW,
    "data-flow-tracer": NARROW + [_GRAPHIFY_BASH],
    "adr-author": RATIONALE,
    "architect": RATIONALE,
    "security-engineer": RATIONALE,
    "platform-engineer": RATIONALE,
    "codebase-recon": RATIONALE,
}

# Team agents the structural sweep surfaces but the mapping deliberately does NOT
# grant (dispatch-only, non-code-structure roles). Exactly the swept agents absent
# from TIER_CONFIG — no more, no less. `session-analysis` and `mutation-kill` carry
# neither marker, so the sweep never surfaces them (they need no exclusion entry;
# mutation-kill is covered via TIER_CONFIG).
EXCLUSIONS = {
    "orchestrator",
    "product-manager",
    "ui-ux-designer",
    "tech-writer",
    "progress-guardian",
}

_BEHAVIORAL_RE = re.compile(r"^##\s+Behavioral Guidelines\s*$", re.MULTILINE)
_ENFORCEMENT_RE = re.compile(r"^Enforcement:\s*script\s*$", re.MULTILINE)


def _agents_dir_default() -> Path:
    return Path(__file__).parent.parent / "agents"


def is_team_agent(text: str) -> bool:
    """True if the file is a team agent per agent-audit §2c's markers.

    A team agent carries a ``## Behavioral Guidelines`` section OR declares
    ``Enforcement: script`` (a body-level declaration, not frontmatter — issue
    #1333 — marking a script-enforced prose spec: still a team agent for
    coverage purposes, just persona-exempt).
    """
    return bool(_BEHAVIORAL_RE.search(text) or _ENFORCEMENT_RE.search(text))


def swept_agents(agents_dir: Path) -> list[str]:
    """Structural sweep (branch b): team agents minus *-review, sorted by stem."""
    out = []
    for path in sorted(agents_dir.glob("*.md")):
        if path.name.endswith("-review.md"):
            continue
        if is_team_agent(path.read_text(encoding="utf-8")):
            out.append(path.stem)
    return out


def _targets(agents_dir: Path) -> dict[str, tuple[Path, list[str]]]:
    return {name: (agents_dir / f"{name}.md", required) for name, required in TIER_CONFIG.items()}


def _unclassified(covered: list[str]) -> list[str]:
    return sorted(name for name in covered if name not in TIER_CONFIG and name not in EXCLUSIONS)


def evaluate(agents_dir: Path) -> dict:
    """Return the mapping report: covered set, offenders, unclassified.

    covered = union of TIER_CONFIG keys (branch a) and the sweep (branch b).
    offenders = {agent: missing tools} for covered config agents under-granted.
    unclassified = swept team agents in neither TIER_CONFIG nor EXCLUSIONS.
    """
    swept = swept_agents(agents_dir)
    covered = sorted(set(TIER_CONFIG) | set(swept))
    offenders, _fixed, _unfixable = run_grants_check(_targets(agents_dir))

    return {
        "covered": covered,
        "swept": swept,
        "offenders": offenders,
        "unclassified": _unclassified(covered),
    }


def apply_fixes(agents_dir: Path) -> dict[str, list[str]]:
    """Append missing tier tools to each under-granted config agent. Returns fixed map.

    Unclassified agents are not auto-fixed (they need a human classification
    decision) — the caller reports them and exits non-zero.
    """
    _offenders, fixed, _unfixable = run_grants_check(_targets(agents_dir), apply_fix=True)
    return fixed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents-dir", type=Path, default=None)
    parser.add_argument("--fix", action="store_true", help="append missing tier tools")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    agents_dir = args.agents_dir or _agents_dir_default()
    if not agents_dir.is_dir():
        print(f"ERROR: agents directory not found: {agents_dir}", file=sys.stderr)
        return 1

    swept = swept_agents(agents_dir)
    covered = sorted(set(TIER_CONFIG) | set(swept))
    offenders, fixed, unfixable = run_grants_check(_targets(agents_dir), apply_fix=args.fix)
    unclassified = _unclassified(covered)
    rc = 1 if (offenders or unclassified) else 0

    if args.json:
        # --json owns stdout: emit ONLY the JSON object.
        report = build_json_report(
            "agent-tool-mapping",
            covered,
            offenders,
            ok=(rc == 0),
            fixed=fixed,
            unfixable=unfixable,
            unclassified=unclassified,
            notes={"swept": swept},
        )
        print(json.dumps(report, indent=2))
        return rc

    if args.fix:
        if fixed:
            for name, added in fixed.items():
                print(f"FIXED: {name} — added {', '.join(added)}")
        else:
            print("OK: all mapped agents already grant their tier tools.")

    if offenders:
        print("FAIL: non-review agents missing their tier's code-intelligence tools:")
        for name, missing in offenders.items():
            print(f"  - {name}: missing {', '.join(missing)}")
        print("\nRun: python3 plugins/dev-team/scripts/check_agent_tool_mapping.py --fix")
    if unclassified:
        print("FAIL: team agents in neither the mapping nor the exclusion list "
              "(classify each into TIER_CONFIG or EXCLUSIONS):")
        for name in unclassified:
            print(f"  - {name}")
    if rc == 0:
        print(f"OK: all {len(covered)} covered agents match the tool mapping.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
