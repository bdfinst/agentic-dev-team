"""Fleet-wide agent frontmatter conventions this repo layers on top of the
optional official Claude Code sub-agent contract (agent-contract.json),
enforced across all three plugin agent directories via the shared
`PLUGIN_AGENTS_DIRS` constant in `tests/agents/_plugin_dirs.py` -- a superset
of `test_agent_effort_frontmatter.py`'s own two-dir scope, since these
conventions were introduced with marketplace-dev in scope from day one.

1. `color:` (ADR 0027) -- every agent must declare a value matching a
   deterministic priority rule, rather than a hand-picked one:

   1. `tools:` contains `Agent` (bare or `Agent(...)`)      -> purple (orchestrator)
   2. Else `tools:` contains `Edit` or `Write`              -> yellow (changes files)
   3. Else name ends `-review` or starts `plan-review-`     -> green (reviewer)
   4. Else                                                  -> cyan (all others)

2. `skills:` preload -- any agent whose body has a `## Skills` section must
   declare a non-empty `skills:` list (issue #1335).

3. `memory: project` -- any agent whose `tools:` includes `Edit` or `Write`
   must declare `memory: project` (issue #1335).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from _plugin_dirs import (
    PLUGIN_AGENTS_DIRS,
    REPO_ROOT,
    frontmatter_and_body,
    frontmatter_block,
    frontmatter_field,
)

ALLOWED_COLORS = ("purple", "yellow", "green", "cyan")


def _agent_files() -> List[Path]:
    files: List[Path] = []
    for agents_dir in PLUGIN_AGENTS_DIRS:
        files.extend(agents_dir.glob("*.md"))
    return sorted(files)


def _has_skills_section(body: str) -> bool:
    return re.search(r"^## Skills\s*$", body, re.MULTILINE) is not None


def _skills_section_text(body: str) -> str:
    """Return just the `## Skills` section's own text (heading to the next
    `## ` heading or end of file) -- scoping the name-traceability check to
    that section rather than a whole-body substring match, which could
    false-positive on a name that merely happens to appear elsewhere in the
    body (e.g. a Knowledge Files section)."""
    match = re.search(r"^## Skills\s*$(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def _skills_list(fm: str) -> List[str]:
    """Parse a `skills:` YAML block-list from an already-extracted frontmatter
    block. Returns [] if the key is absent or has no list items. Assumes
    2-space indentation on each item -- every agent's skills: list in this
    fleet is written that way (verified by the real-file sweep test below);
    a differently-indented list would silently parse as empty rather than
    error, so this is a load-bearing formatting assumption, not a detail."""
    match = re.search(r"^skills:\s*\n((?:^  - .+\n?)+)", fm, re.MULTILINE)
    if not match:
        return []
    return [line.strip()[2:].strip() for line in match.group(1).splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# color: (ADR 0027)
# ---------------------------------------------------------------------------


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


def test_rule_agent_word_boundary_guards_incidental_substring() -> None:
    """An incidental 'Agent' substring that is NOT the bare Agent tool (e.g.
    a hypothetical 'AgentReview' token) must not resolve purple -- locks the
    word-boundary regex the docstring calls load-bearing (ADR 0027 branch 1)
    against a future 'simplify to "Agent" in tools' regression."""
    fake_path = Path("some-utility.md")
    expected = compute_expected_color(fake_path, "Read, AgentReview, Grep")
    assert expected != "purple"


def test_classify_missing_color_is_flagged() -> None:
    reason = classify_declared_color("", "cyan")
    assert reason is not None and "missing color:" in reason and "cyan" in reason


def test_classify_valid_contract_color_outside_mechanical_set_is_flagged() -> None:
    """`red` is a valid agent-contract.json color but not one of the 4
    mechanical colors this rule can produce -- must still be rejected."""
    reason = classify_declared_color("red", "cyan")
    assert reason is not None and "red" in reason and "not one of" in reason


def test_classify_mismatched_valid_color_is_flagged() -> None:
    """`declared` IS one of ALLOWED_COLORS but differs from the rule-computed
    `expected` -- the third violation branch, distinct from missing/invalid."""
    reason = classify_declared_color("green", "yellow")
    assert (
        reason is not None
        and "green" in reason
        and "yellow" in reason
        and "rule computes" in reason
    )


def test_classify_compliant_color_passes() -> None:
    assert classify_declared_color("yellow", "yellow") is None


# ---------------------------------------------------------------------------
# skills: preload (issue #1335)
# ---------------------------------------------------------------------------


def classify_skills_declaration(declared: List[str], skills_section_text: str) -> Optional[str]:
    """Return a violation reason for one agent's skills: declaration against
    its own `## Skills` section text, or None if compliant. Pure function --
    no filesystem access -- so the missing/unknown-name branches are
    unit-testable without needing a real agent file in that state. Callers
    only invoke this for agents that have a `## Skills` section at all.
    """
    if not declared:
        return "has a ## Skills section but no skills: frontmatter"
    # Each declared name must actually appear in the section's own text --
    # guards against a stale/hallucinated entry that doesn't trace back to
    # the section (scoped to the section, not the whole body, so a name that
    # merely appears elsewhere -- e.g. Knowledge Files -- doesn't pass).
    unknown = [name for name in declared if name not in skills_section_text]
    if unknown:
        return f"skills: names not found in the ## Skills section: {unknown}"
    return None


def test_every_agent_with_a_skills_section_declares_skills_frontmatter() -> None:
    files = _agent_files()
    assert files, "No agent files found under PLUGIN_AGENTS_DIRS — check the glob paths."

    violations = []
    for agent_file in files:
        fm, body = frontmatter_and_body(agent_file)
        if not _has_skills_section(body):
            continue
        declared = _skills_list(fm)
        rel = agent_file.relative_to(REPO_ROOT)
        reason = classify_skills_declaration(declared, _skills_section_text(body))
        if reason is not None:
            violations.append(f"{rel}: {reason}")

    assert not violations, (
        "Agent skills: preload contract violated (issue #1335). Every agent "
        "with a '## Skills' section must declare a non-empty skills: list "
        "whose names trace back to that section.\n  " + "\n  ".join(violations)
    )


def test_classify_skills_missing_declaration_is_flagged() -> None:
    reason = classify_skills_declaration([], "- [Foo](../skills/foo/SKILL.md)")
    assert reason is not None and "no skills: frontmatter" in reason


def test_classify_skills_unknown_name_is_flagged() -> None:
    reason = classify_skills_declaration(["foo", "bar"], "- [Foo](../skills/foo/SKILL.md)")
    assert (
        reason is not None
        and "bar" in reason
        and "not found" in reason
        and "foo" not in reason  # the known/traceable name must not also be flagged
    )


def test_classify_skills_name_outside_section_is_flagged() -> None:
    """Given a section text that doesn't contain a declared name, that name
    is flagged -- the comparison classify_skills_declaration itself performs.
    (The separate boundary test below proves the section text handed to this
    function is actually scoped correctly; this test doesn't call
    _skills_section_text at all.)"""
    reason = classify_skills_declaration(["agent-eval"], "- [Foo](../skills/foo/SKILL.md)")
    assert reason is not None and "agent-eval" in reason


def test_classify_skills_compliant_passes() -> None:
    assert classify_skills_declaration(["foo"], "- [Foo](../skills/foo/SKILL.md)") is None


def test_skills_section_text_stops_at_the_next_heading() -> None:
    """Proves _skills_section_text's non-greedy boundary: a name that exists
    only in a later section (e.g. Knowledge Files, which follows ## Skills in
    several real agents) must NOT be swept into the Skills section's text --
    an over-capturing regex would silently make classify_skills_declaration
    stop flagging stale names, and no other test would catch that."""
    body = (
        "## Skills\n\n- [Foo](../skills/foo/SKILL.md)\n\n"
        "## Knowledge Files\n\n- [Bar](../skills/bar/SKILL.md)\n"
    )
    section = _skills_section_text(body)
    assert "Foo" in section
    assert "Bar" not in section


def test_skills_list_parses_a_block_form_list() -> None:
    fm = "name: fake\nskills:\n  - foo\n  - bar\n"
    assert _skills_list(fm) == ["foo", "bar"]


def test_skills_list_empty_when_key_absent() -> None:
    assert _skills_list("name: fake\n") == []


# ---------------------------------------------------------------------------
# memory: project (issue #1335)
# ---------------------------------------------------------------------------


def classify_memory_declaration(memory: str, tools: str) -> Optional[str]:
    """Return a violation reason for one agent's memory: declaration against
    its tools:, or None if compliant (including "not applicable" for a
    non-file-mutating agent). Pure function -- no filesystem access -- so
    the missing/mismatched/not-applicable branches are unit-testable
    without needing a real agent file in that state.
    """
    if "Edit" not in tools and "Write" not in tools:
        return None
    if memory != "project":
        return f"tools: includes Edit/Write but memory: is {memory!r} (expected 'project')"
    return None


def test_every_file_mutating_agent_declares_memory_project() -> None:
    files = _agent_files()
    assert files, "No agent files found under PLUGIN_AGENTS_DIRS — check the glob paths."

    violations = []
    for agent_file in files:
        fm = frontmatter_block(agent_file)
        tools = frontmatter_field(fm, "tools")
        memory = frontmatter_field(fm, "memory")
        rel = agent_file.relative_to(REPO_ROOT)
        reason = classify_memory_declaration(memory, tools)
        if reason is not None:
            violations.append(f"{rel}: {reason}")

    assert not violations, (
        "Agent memory: project contract violated (issue #1335). Every "
        "file-mutating agent (Edit/Write in tools:) must declare "
        "memory: project.\n  " + "\n  ".join(violations)
    )


def test_classify_memory_missing_is_flagged() -> None:
    reason = classify_memory_declaration("", "Read, Grep, Glob, Edit")
    assert reason is not None and "expected 'project'" in reason and "''" in reason


def test_classify_memory_wrong_value_is_flagged() -> None:
    reason = classify_memory_declaration("user", "Read, Write")
    assert reason is not None and "'user'" in reason


def test_classify_memory_non_mutating_agent_not_applicable() -> None:
    assert classify_memory_declaration("", "Read, Grep, Glob") is None


def test_classify_memory_compliant_passes() -> None:
    assert classify_memory_declaration("project", "Read, Edit, Write") is None
