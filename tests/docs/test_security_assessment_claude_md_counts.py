"""Regression guard for security-assessment/CLAUDE.md's item-count prose (#1389).

`plugins/security-assessment/CLAUDE.md`'s "Dispatch registry" section hand-states
a count in each of its `**<Category>** (N...)` headers (`**Agents** (13, effort:
high)`, `**Skills** (3)`, `**Commands** (5)`, `**Hooks** (3)`, `**Knowledge** (9)`).
Nothing previously pinned these against disk, so an added/removed agent, skill,
command, hook, or knowledge file could silently drift the stated N with nothing
failing CI — exactly the class of drift a prior PR hand-fixed once already
(Hooks 2->3, Knowledge 4->9) with no regression guard behind the fix.

Sibling to `test_plugin_agent_catalog_freshness.py`, which pins the same plugin's
`docs/agent_info.md` table against disk — this file pins the CLAUDE.md prose
counts instead, since that is a second, independently-drifting source of truth
for the same underlying file counts.

`knowledge/` count is top-level files only. `knowledge/semgrep-rules/` is a
subdirectory documented as its own (uncounted) bullet in the CLAUDE.md prose —
its 4-file YAML ruleset is described inline (`{ml-patterns,llm-safety,...}.yaml`)
rather than as individual top-level knowledge files, and `knowledge/fixtures/` +
`knowledge/rule-fixtures/` are semgrep test fixtures, not knowledge references
agents load — so both exclusion classes are directories, already outside this
file's `iterdir()` `is_file()` filter, and are never counted.
"""

from __future__ import annotations

import re
from pathlib import Path

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "security-assessment"
CLAUDE_MD = PLUGIN_ROOT / "CLAUDE.md"
CLAUDE_MD_TEXT = CLAUDE_MD.read_text(encoding="utf-8")

# Matches "**Agents** (13, effort: high):" or "**Skills** (3):" — captures the
# category label and the leading integer inside the parens, tolerant of any
# trailing qualifier text before the close-paren.
_HEADER_RE = re.compile(r"\*\*(Agents|Skills|Commands|Hooks|Knowledge)\*\*\s*\((\d+)")


def _stated_counts() -> dict[str, int]:
    counts = {m.group(1): int(m.group(2)) for m in _HEADER_RE.finditer(CLAUDE_MD_TEXT)}
    assert counts.keys() == {"Agents", "Skills", "Commands", "Hooks", "Knowledge"}, (
        f"expected exactly one count header per category, got {sorted(counts)}"
    )
    return counts


def _actual_agents() -> int:
    return len(list((PLUGIN_ROOT / "agents").glob("*.md")))


def _actual_skills() -> int:
    return len(list((PLUGIN_ROOT / "skills").glob("*/SKILL.md")))


def _actual_commands() -> int:
    return len(list((PLUGIN_ROOT / "commands").glob("*.md")))


def _actual_top_level_files(directory: Path) -> int:
    return sum(1 for p in directory.iterdir() if p.is_file())


def test_claude_md_states_exactly_one_count_per_category() -> None:
    _stated_counts()  # asserts the keys itself; call for its own failure message


def test_agents_count_matches_disk() -> None:
    stated = _stated_counts()["Agents"]
    actual = _actual_agents()
    assert stated == actual, (
        f"CLAUDE.md states **Agents** ({stated}, ...) but {actual} agents/*.md files exist on disk"
    )


def test_skills_count_matches_disk() -> None:
    stated = _stated_counts()["Skills"]
    actual = _actual_skills()
    assert stated == actual, (
        f"CLAUDE.md states **Skills** ({stated}) but {actual} skills/*/SKILL.md files exist on disk"
    )


def test_commands_count_matches_disk() -> None:
    stated = _stated_counts()["Commands"]
    actual = _actual_commands()
    assert stated == actual, (
        f"CLAUDE.md states **Commands** ({stated}) but {actual} commands/*.md files exist on disk"
    )


def test_hooks_count_matches_disk() -> None:
    stated = _stated_counts()["Hooks"]
    actual = _actual_top_level_files(PLUGIN_ROOT / "hooks")
    assert stated == actual, (
        f"CLAUDE.md states **Hooks** ({stated}) but {actual} top-level files exist in hooks/"
    )


def test_knowledge_count_matches_disk_top_level_files_only() -> None:
    """Excludes knowledge/semgrep-rules/, knowledge/fixtures/, knowledge/rule-fixtures/
    (all subdirectories, documented separately in CLAUDE.md's prose, not counted)."""
    stated = _stated_counts()["Knowledge"]
    actual = _actual_top_level_files(PLUGIN_ROOT / "knowledge")
    assert stated == actual, (
        f"CLAUDE.md states **Knowledge** ({stated}) but {actual} top-level files exist in "
        f"knowledge/ (excluding subdirectories)"
    )


def test_every_stated_agent_count_is_a_positive_integer() -> None:
    for label, value in _stated_counts().items():
        assert value > 0, f"{label} count parsed as {value}, expected a positive integer"
