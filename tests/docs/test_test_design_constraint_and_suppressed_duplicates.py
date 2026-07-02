"""Structural contract for /test-design constraint 3 and its report
template (#534). Constraint 3 no longer proposes report-time
de-duplication of smell/advisor remedies; findings join structurally on
remedyFamily. The report template gains a Suppressed duplicates section
for any drops constraint 3 still performs (mechanics overlap between
test-review and test-smell-review).

Ported from tests/docs/test_design_constraint_and_suppressed_duplicates_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design" / "SKILL.md"


def _section(text: str, start_pattern: str, end_pattern: str) -> str:
    lines = text.splitlines()
    collected = []
    in_section = False
    for line in lines:
        if re.match(start_pattern, line):
            in_section = True
        if in_section:
            collected.append(line)
        if (
            in_section
            and re.match(end_pattern, line)
            and not re.match(start_pattern, line)
        ):
            break
    return "\n".join(collected)


def test_test_design_skill_exists() -> None:
    assert SKILL.is_file()


def test_constraint_3_states_structural_join_on_remedy_family() -> None:
    # The phrase may span two lines (word-wrap); flatten to one line before
    # matching so the regex isn't foiled by hard wraps.
    text = SKILL.read_text(encoding="utf-8")
    section = _section(text, r"^3\. \*\*No double-reporting", r"^4\. ")
    flat = section.replace("\n", " ")
    assert re.search(r"join +structurally|structural +join", flat, re.IGNORECASE)
    assert "remedyFamily" in flat


def test_constraint_3_no_longer_proposes_report_time_deduplication() -> None:
    # The removed language: "preferring the advisor's forward-looking
    # sequence when it subsumes the smell-review note". Must not survive.
    text = SKILL.read_text(encoding="utf-8")
    assert not re.search(
        r"preferring the advisor.*forward-looking sequence|"
        r"advisor.*subsumes.*smell-review",
        text,
        re.IGNORECASE,
    )


def test_constraint_3_still_keeps_test_review_test_smell_review_rule() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert re.search(
        r"test-review.*test-smell-review|test-smell-review.*test-review",
        text,
        re.IGNORECASE,
    )


def test_report_template_includes_suppressed_duplicates_section() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "### Suppressed duplicates" in text


def test_suppressed_duplicates_section_documents_none_default() -> None:
    # Reads '_None._' (italic) by default when nothing was dropped.
    text = SKILL.read_text(encoding="utf-8")
    assert "_None._" in text


def test_suppressed_duplicates_section_documents_entry_format() -> None:
    # Extract the report-template Suppressed-duplicates block. The heading
    # occurs in two places (once inside constraint 3's backtick prose, once
    # as the template heading); we grab lines from every
    # ### Suppressed duplicates occurrence onward to end of file, which is
    # sufficient — the entry-format documentation must live in at least one
    # of them.
    text = SKILL.read_text(encoding="utf-8")
    section = _section(text, r"^### Suppressed duplicates", r"^### Next steps")
    assert re.search(r"file:line", section, re.IGNORECASE)
    assert re.search(r"dropped", section, re.IGNORECASE)
    assert re.search(r"reason|why", section, re.IGNORECASE)
