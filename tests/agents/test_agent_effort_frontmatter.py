"""ADR 0008: every agent — current and future — must declare a valid `effort:`
band in its YAML frontmatter. This gate fails CI if any agent file is missing
the field or carries a value outside the allowed set, so the contract cannot
silently rot the way `model: mid` did under the old vendor-named scheme.

Allowed bands are the single source of truth below; extend here (and in the
resolver) if a new band is added.

Extended (issue #1040) to also gate:
- Deprecated `model: haiku|sonnet|opus` tier field in frontmatter (must be
  absent — use `effort:` instead).
- Colon character in `description:` frontmatter field (breaks argument-hints
  and other tooling — per agent-audit SKILL.md check 10).
- `Context needs: diff-only|full-file|project-structure` declaration anywhere
  in the agent body (per agent-audit SKILL.md check 9).

All checks cover both plugins/dev-team/agents/ and
plugins/security-assessment/agents/. Add new plugin agent directories to
AGENTS_DIRS when a new plugin is introduced.

Ported from tests/agents/agent_effort_frontmatter_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIRS = [
    REPO_ROOT / "plugins" / "dev-team" / "agents",
    REPO_ROOT / "plugins" / "security-assessment" / "agents",
]
ALLOWED_BANDS = ("low", "medium", "high")
DEPRECATED_MODEL_TIERS = ("haiku", "sonnet", "opus")
ALLOWED_CONTEXT_NEEDS = ("diff-only", "full-file", "project-structure", "artifact-stream")


def _agent_files_to_check(agent_files: str | None = None) -> List[Path]:
    """Resolve which agent files to check.

    - Default: every *.md directly under any agents/ directory in AGENTS_DIRS.
    - With agent_files: only the named basenames (each must exist in one of the dirs).
    """
    if agent_files:
        raw = agent_files.replace(",", " ").split()
        result = []
        for name in raw:
            found = None
            for agents_dir in AGENTS_DIRS:
                candidate = agents_dir / name
                if candidate.is_file():
                    found = candidate
                    break
            if found is None:
                raise ValueError(f"AGENT_FILES contains an unknown agent: {name}")
            result.append(found)
        return result
    files: List[Path] = []
    for agents_dir in AGENTS_DIRS:
        files.extend(agents_dir.glob("*.md"))
    return sorted(files)


def _effort_value(agent_file: Path) -> str:
    """Extract the value of `effort:` from the leading YAML frontmatter block
    only (between the first two `---` fences). Returns the bare value, or ""
    if the key is absent. Trailing inline comments and surrounding whitespace
    are stripped; quotes are removed.
    """
    lines = agent_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return ""
    for line in lines[1:]:
        if line == "---":
            break
        match = re.match(r"^\s*effort\s*:\s*(.*)$", line)
        if match:
            value = match.group(1)
            value = re.sub(r"\s*#.*$", "", value)
            value = value.strip().strip("\"'").strip()
            return value
    return ""


def _frontmatter_field(agent_file: Path, field: str) -> str:
    """Extract a frontmatter field value (stripped, unquoted). Returns '' if absent."""
    lines = agent_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return ""
    for line in lines[1:]:
        if line == "---":
            break
        match = re.match(rf"^\s*{re.escape(field)}\s*:\s*(.*)$", line)
        if match:
            value = match.group(1)
            value = re.sub(r"\s*#.*$", "", value)
            return value.strip().strip("\"'").strip()
    return ""


def _context_needs_value(agent_file: Path) -> str:
    """Extract the value after 'Context needs:' anywhere in the file body.

    Scans outside frontmatter only; returns '' if absent.
    """
    lines = agent_file.read_text(encoding="utf-8").splitlines()
    body_start = 0
    if lines and lines[0] == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line == "---":
                body_start = i + 1
                break
    for line in lines[body_start:]:
        match = re.match(r"^\s*Context needs\s*:\s*(.*)$", line)
        if match:
            return match.group(1).strip()
    return ""


def test_agent_files_typo_guard_unknown_filename_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown agent: does-not-exist.md"):
        _agent_files_to_check("does-not-exist.md")


def test_adr_0008_every_agent_declares_a_valid_effort_band() -> None:
    files = _agent_files_to_check()

    missing = []
    invalid = []
    for agent_file in files:
        value = _effort_value(agent_file)
        rel = agent_file.relative_to(REPO_ROOT)
        if not value:
            missing.append(str(rel))
            continue
        if value not in ALLOWED_BANDS:
            invalid.append(f"{rel}: effort: {value}")

    assert not missing and not invalid, (
        "Agent effort-band contract violated (ADR 0008). Every agent must "
        f"declare 'effort: <band>' where <band> is one of: {' '.join(ALLOWED_BANDS)}.\n"
        f"Missing effort: field:\n  " + "\n  ".join(missing) + "\n"
        "Invalid effort: value:\n  " + "\n  ".join(invalid)
    )


def test_no_deprecated_model_tier() -> None:
    """FAIL if any agent declares a legacy model: haiku|sonnet|opus tier.

    The deprecated `model:` field has been superseded by `effort:` (ADR 0008).
    Remove `model:` from the frontmatter and rely on the effort band instead.
    """
    files = _agent_files_to_check()
    violations = []
    for agent_file in files:
        model_val = _frontmatter_field(agent_file, "model")
        if model_val.lower() in DEPRECATED_MODEL_TIERS:
            rel = agent_file.relative_to(REPO_ROOT)
            violations.append(f"{rel}: model: {model_val}")

    assert not violations, (
        "Deprecated model: tier found (superseded by effort:). "
        "Remove the model: line from frontmatter — "
        f"haiku→low, sonnet→medium, opus→high.\n"
        "Violations:\n  " + "\n  ".join(violations)
    )


def test_description_has_no_colon() -> None:
    """FAIL if any agent description: frontmatter field contains a colon.

    Colons in description break argument-hints and other tooling that parses
    the field as a simple string (agent-audit SKILL.md check 10).
    """
    files = _agent_files_to_check()
    violations = []
    for agent_file in files:
        desc = _frontmatter_field(agent_file, "description")
        if ":" in desc:
            rel = agent_file.relative_to(REPO_ROOT)
            violations.append(f"{rel}: description contains colon: {desc[:80]}")

    assert not violations, (
        "Agent description: field must not contain colons. "
        "Replace ':' with '-' or reword (agent-audit SKILL.md check 10).\n"
        "Violations:\n  " + "\n  ".join(violations)
    )


def test_every_agent_declares_context_needs() -> None:
    """FAIL if any agent body is missing a 'Context needs:' declaration.

    Every agent must declare one of: diff-only, full-file, project-structure,
    artifact-stream (or a comma-separated combination of recognized values).
    This tells the orchestrator how much context to load before dispatching
    (agent-audit SKILL.md check 9).
    """
    files = _agent_files_to_check()
    missing = []
    invalid = []
    for agent_file in files:
        value = _context_needs_value(agent_file)
        rel = agent_file.relative_to(REPO_ROOT)
        if not value:
            missing.append(str(rel))
            continue
        # Strip inline notes (e.g. "full-file (reads plan + git state)").
        # Support comma-separated combined values like "artifact-stream, full-file".
        # canonical source: agent-audit/SKILL.md check 9
        tokens = [t.strip().split()[0] for t in value.split(",")]
        if any(t not in ALLOWED_CONTEXT_NEEDS for t in tokens):
            invalid.append(f"{rel}: Context needs: {value}")

    assert not missing and not invalid, (
        "Agent Context needs contract violated. Every agent body must declare "
        f"'Context needs: <scope>' where <scope> is one of: "
        f"{'  '.join(ALLOWED_CONTEXT_NEEDS)}.\n"
        "Missing Context needs:\n  " + "\n  ".join(missing) + "\n"
        "Invalid Context needs value:\n  " + "\n  ".join(invalid)
    )
