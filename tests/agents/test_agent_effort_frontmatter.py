"""ADR 0008: every agent — current and future — must declare a valid `effort:`
band in its YAML frontmatter. This gate fails CI if any agent file is missing
the field or carries a value outside the allowed set, so the contract cannot
silently rot the way `model: mid` did under the old vendor-named scheme.

Allowed bands are the single source of truth below; extend here (and in the
resolver) if a new band is added.

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
