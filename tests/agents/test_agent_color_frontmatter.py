"""ADR 0027: every agent — current and future — must declare a `color:` in
its YAML frontmatter that matches a deterministic, mechanically computed
rule, rather than a hand-picked value. `color:` is optional in the official
Claude Code sub-agent contract (agent-contract.json); this repo layers a
required-and-derived convention on top of it, the same category as the
`effort: high` convention (ADR 0026).

Priority order (capability checked before naming, so what an agent can do
outranks what it's called):

1. `tools:` contains `Agent` (bare or `Agent(...)`)      -> purple (orchestrator)
2. Else `tools:` contains `Edit` or `Write`              -> yellow (changes files)
3. Else name ends `-review` or starts `plan-review-`     -> green (reviewer)
4. Else                                                  -> cyan (all others)

Covers all three plugin agent directories (dev-team, security-assessment,
marketplace-dev) via the shared `PLUGIN_AGENTS_DIRS` constant in
`tests/agents/_plugin_dirs.py` — a superset of
`test_agent_effort_frontmatter.py`'s own two-dir list, since color is a new
fleet-wide convention introduced with marketplace-dev in scope from day one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from _plugin_dirs import PLUGIN_AGENTS_DIRS, REPO_ROOT, frontmatter_block, frontmatter_field

ALLOWED_COLORS = ("purple", "yellow", "green", "cyan")


def _agent_files() -> List[Path]:
    files: List[Path] = []
    for agents_dir in PLUGIN_AGENTS_DIRS:
        files.extend(agents_dir.glob("*.md"))
    return sorted(files)


def compute_expected_color(agent_file: Path, tools: str) -> str:
    """Return the rule-computed color for one agent, per ADR 0027's priority order."""
    name = agent_file.stem
    # Word-boundary guards distinguish the bare `Agent` tool (or `Agent(...)`)
    # from an incidental "Agent" substring elsewhere on the tools: line -- a
    # naive `"Agent" in tools` would misfire (see ADR 0027 branch 1).
    has_agent_tool = re.search(r"(?<![A-Za-z])Agent(?![A-Za-z(])|Agent\(", tools) is not None
    has_edit_or_write = "Edit" in tools or "Write" in tools
    is_review_named = name.endswith("-review") or name.startswith("plan-review-")

    if has_agent_tool:
        return "purple"
    if has_edit_or_write:
        return "yellow"
    if is_review_named:
        return "green"
    return "cyan"


def classify_declared_color(declared: str, expected: str) -> Optional[str]:
    """Return a violation reason for one agent's declared vs. expected color,
    or None if it's compliant. Pure function -- no filesystem access -- so
    the missing/invalid/mismatched branches are unit-testable without needing
    a real agent file in that state.
    """
    if not declared:
        return f"missing color: (expected {expected})"
    if declared not in ALLOWED_COLORS:
        return f"color: {declared} is not one of {ALLOWED_COLORS}"
    if declared != expected:
        return f"color: {declared}, but the rule computes {expected}"
    return None


def test_every_agent_declares_the_rule_computed_color() -> None:
    files = _agent_files()
    assert files, "No agent files found under PLUGIN_AGENTS_DIRS — check the glob paths."

    missing = []
    mismatched = []
    for agent_file in files:
        fm = frontmatter_block(agent_file)
        tools = frontmatter_field(fm, "tools")
        declared = frontmatter_field(fm, "color")
        expected = compute_expected_color(agent_file, tools)
        rel = agent_file.relative_to(REPO_ROOT)
        reason = classify_declared_color(declared, expected)
        if reason is None:
            continue
        if not declared:
            missing.append(f"{rel}: {reason}")
        else:
            mismatched.append(f"{rel}: {reason}")

    assert not missing and not mismatched, (
        "Agent color contract violated (ADR 0027). Every agent must declare "
        "'color:' matching the mechanical priority rule (Agent tool -> purple, "
        "Edit/Write -> yellow, *-review/plan-review-* name -> green, else cyan).\n"
        "Missing color::\n  " + "\n  ".join(missing) + "\n"
        "Mismatched color::\n  " + "\n  ".join(mismatched)
    )


def test_rule_priority_capability_outranks_naming() -> None:
    """A hypothetical file-mutating agent named like a reviewer resolves yellow,
    not green -- capability wins over the naming heuristic (ADR 0027)."""
    fake_path = Path("auto-fix-review.md")
    expected = compute_expected_color(fake_path, "Read, Grep, Glob, Edit")
    assert expected == "yellow"


def test_rule_agent_tool_outranks_everything() -> None:
    """An agent with the Agent tool resolves purple even if it's also
    review-named and file-mutating -- rule branch 1 wins outright."""
    fake_path = Path("plan-review-fake.md")
    expected = compute_expected_color(fake_path, "Read, Edit, Write, Agent")
    assert expected == "purple"


def test_rule_default_cyan_when_no_branch_matches() -> None:
    """An agent matching none of the capability/naming branches resolves cyan."""
    fake_path = Path("some-utility.md")
    expected = compute_expected_color(fake_path, "Read, Grep, Glob, Skill")
    assert expected == "cyan"


def test_classify_missing_color_is_flagged() -> None:
    reason = classify_declared_color("", "cyan")
    assert reason is not None and "missing color:" in reason and "cyan" in reason


def test_classify_valid_contract_color_outside_mechanical_set_is_flagged() -> None:
    """`red` is a valid agent-contract.json color but not one of the 4
    mechanical colors this rule can produce -- must still be rejected."""
    reason = classify_declared_color("red", "cyan")
    assert reason is not None and "red" in reason and "not one of" in reason


def test_classify_compliant_color_passes() -> None:
    assert classify_declared_color("yellow", "yellow") is None
