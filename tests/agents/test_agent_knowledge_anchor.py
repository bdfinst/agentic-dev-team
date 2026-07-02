"""Every knowledge-file or skill reference in an agent body either cites a
section anchor that exists in knowledge/index.json, OR the paragraph
containing the reference contains the literal verbatim token
"Whole-file load:" (case-sensitive, hyphen, colon).

Ported from tests/agents/agent_knowledge_anchor_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "index.json"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
WHOLE_FILE_TOKEN = "Whole-file load:"

# Pattern: dev-team's own knowledge/<name>.md or skills/<name>/SKILL.md.
# Excludes cross-plugin references (e.g.
# `plugins/security-assessment/skills/...`). A reference belongs to this
# index iff it's either bare `knowledge/X.md` / `skills/Y/SKILL.md` OR
# explicitly prefixed with `plugins/dev-team/`. Cross-plugin paths start
# with `plugins/<other>/`, so we require either no prefix or our plugin
# prefix.
REF_RE = re.compile(
    r"(?:^|[^/])"
    r"(?:plugins/dev-team/)?"
    r"((?:knowledge/[a-z0-9-]+\.md|skills/[a-z0-9-]+/SKILL\.md))"
    r"(#[a-z0-9-]+)?"
)


def _agent_files_to_check(agent_files: str | None = None) -> List[Path]:
    """Resolve which agent files to check.

    - Default: every *.md under agents/.
    - With agent_files: only the named basenames (each must exist).
    """
    if agent_files:
        raw = agent_files.replace(",", " ").split()
        result = []
        for name in raw:
            candidate = AGENTS_DIR / name
            if not candidate.is_file():
                raise ValueError(f"AGENT_FILES contains an unknown agent: {name}")
            result.append(candidate)
        return result
    return sorted(AGENTS_DIR.glob("*.md"))


def _violations_for_file(agent_file: Path, index: dict) -> List[str]:
    text = agent_file.read_text(encoding="utf-8")
    paragraphs = re.split(r"\n\s*\n", text)

    violations = []
    for para in paragraphs:
        for m in REF_RE.finditer(para):
            ref_file = m.group(1)
            anchor = m.group(2)
            start = m.start()
            pre = para[max(0, start - 60) : start]
            cross_plugin = re.search(r"plugins/(?!dev-team/)[a-z0-9-]+/$", pre)
            if cross_plugin:
                continue
            key = f"plugins/dev-team/{ref_file}"
            if anchor:
                anchor_slug = anchor.lstrip("#")
                section_data = index.get(key, {})
                anchors = {entry.get("anchor") for entry in section_data.values()}
                if anchor_slug in anchors:
                    continue
                violations.append(
                    f"{agent_file}: anchor '{anchor_slug}' not found in {key}"
                )
                continue
            if WHOLE_FILE_TOKEN in para:
                continue
            violations.append(
                f"{agent_file}: bare reference {ref_file} lacks an anchor AND "
                f"no '{WHOLE_FILE_TOKEN}' in paragraph"
            )
    return violations


def test_agent_files_typo_guard_unknown_filename_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown agent: does-not-exist.md"):
        _agent_files_to_check("does-not-exist.md")


def test_every_knowledge_skill_reference_cites_valid_anchor_or_whole_file_load() -> (
    None
):
    files = _agent_files_to_check()
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    violations: List[str] = []
    for agent_file in files:
        violations.extend(_violations_for_file(agent_file, index))

    assert not violations, (
        "Anchor-citation violations found. Every knowledge/X.md or "
        "skills/Y/SKILL.md reference in agents/ must:\n"
        "  - end with a #anchor fragment that exists in knowledge/index.json, OR\n"
        f"  - have the literal verbatim token '{WHOLE_FILE_TOKEN}' in the same "
        "paragraph.\n\n" + "\n".join(violations)
    )
