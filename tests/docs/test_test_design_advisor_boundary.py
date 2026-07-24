"""Structural contract for the test-design-advisor SKILL (#534).

Under /test-design, the smell agent has already named the smell and its
family; Steps 3b and 3c supply the specific remedy pattern.

Ported from tests/docs/test_design_advisor_boundary_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

SKILL = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design-advisor" / "SKILL.md"
)


def _section(text: str, start_pattern: str, end_pattern: str) -> str:
    lines = text.splitlines()
    collected = []
    in_section = False
    for line in lines:
        if re.search(start_pattern, line):
            in_section = True
        if in_section:
            collected.append(line)
        if (
            in_section
            and re.search(end_pattern, line)
            and not re.search(start_pattern, line)
        ):
            break
    return "\n".join(collected)


def test_advisor_skill_exists() -> None:
    assert SKILL.is_file()


def test_step_3b_acknowledges_smell_review_boundary() -> None:
    # A sentence within the fixture-remedy step stating that under
    # /test-design the smell agent has already named the smell and its
    # family. The check spans Step 3b's paragraph; both cues must appear in
    # the file and near each other (verified by doc-lint gate).
    text = SKILL.read_text(encoding="utf-8")
    section = _section(text, r"^### 3b\.", r"^### 3c\.")
    assert re.search(
        r"under.*/test-design.*smell.*(named|already)|"
        r"smell agent.*(already|has).*named",
        section,
        re.IGNORECASE,
    )
    assert re.search(r"family|remedyFamily", section, re.IGNORECASE)


def test_step_3c_acknowledges_smell_review_boundary() -> None:
    text = SKILL.read_text(encoding="utf-8")
    section = _section(text, r"^### 3c\.", r"^### 4\.")
    assert re.search(
        r"under.*/test-design.*smell.*(named|already)|"
        r"smell agent.*(already|has).*named",
        section,
        re.IGNORECASE,
    )
    assert re.search(r"family|remedyFamily", section, re.IGNORECASE)
