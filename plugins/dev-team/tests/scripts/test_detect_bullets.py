"""Unit tests for scripts/lib/detect_bullets.py.

Behavioural: each function takes agent-markdown text and returns plain data.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import detect_bullets

# ---------------------------------------------------------------------------
# bullet_blocks
# ---------------------------------------------------------------------------


def test_single_line_bullets_become_one_block_each():
    section = "- first [MECHANICAL]\n- second [JUDGMENT]\n"
    assert detect_bullets.bullet_blocks(section) == [
        "- first [MECHANICAL]",
        "- second [JUDGMENT]",
    ]


def test_indented_continuation_lines_fold_into_their_bullet():
    section = "- wrapped bullet\n  carries on here\n\tand here [MECHANICAL]\n- next\n"
    assert detect_bullets.bullet_blocks(section) == [
        "- wrapped bullet\n  carries on here\n\tand here [MECHANICAL]",
        "- next",
    ]


def test_nested_bullet_belongs_to_its_top_level_parent():
    section = "- parent\n  - child one\n  - child two [JUDGMENT]\n- sibling\n"
    assert detect_bullets.bullet_blocks(section) == [
        "- parent\n  - child one\n  - child two [JUDGMENT]",
        "- sibling",
    ]


def test_blank_line_and_bare_paragraph_end_a_bullet():
    section = "- bullet\n\n**Consolidation rule** [MECHANICAL]: text\n- later\n"
    assert detect_bullets.bullet_blocks(section) == ["- bullet", "- later"]


def test_section_without_bullets_yields_no_blocks():
    assert detect_bullets.bullet_blocks("just prose\n\nmore prose\n") == []


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


def test_tags_returns_every_tag_in_order_of_appearance():
    assert detect_bullets.tags("- x [JUDGMENT] y [MECHANICAL]") == [
        "JUDGMENT",
        "MECHANICAL",
    ]


@pytest.mark.parametrize("text", ["- plain", "- [mechanical] wrong case", "- [OTHER]"])
def test_tags_ignores_text_that_is_not_an_exact_tag(text):
    assert detect_bullets.tags(text) == []


# ---------------------------------------------------------------------------
# section_between
# ---------------------------------------------------------------------------


def test_section_between_returns_text_between_the_two_markers():
    text = "a\n## Start\nbody\n## End\nz\n"
    assert detect_bullets.section_between(text, "## Start", "## End") == "\nbody\n"


def test_section_between_raises_when_a_marker_is_missing():
    with pytest.raises(ValueError):
        detect_bullets.section_between("no markers", "## Start", "## End")


# ---------------------------------------------------------------------------
# detect_bullets
# ---------------------------------------------------------------------------

AGENT = """\
# Agent

## Detect

- Single line check. [MECHANICAL]
- Multi-line check that
  wraps onto a second line. [JUDGMENT]
- Parent check
  - nested detail [MECHANICAL]

### Subsection heading stays inside Detect

- Bullet under a subsection. [JUDGMENT]

## Output

- Not a Detect bullet. [MECHANICAL]
"""


def test_detect_bullets_collects_top_level_bullets_up_to_the_next_h2():
    found = detect_bullets.detect_bullets(AGENT)
    assert [b.text.splitlines()[0] for b in found] == [
        "- Single line check. [MECHANICAL]",
        "- Multi-line check that",
        "- Parent check",
        "- Bullet under a subsection. [JUDGMENT]",
    ]


def test_detect_bullet_carries_its_one_based_start_line_and_tags():
    found = detect_bullets.detect_bullets(AGENT)
    assert [(b.line, b.tags) for b in found] == [
        (5, ["MECHANICAL"]),
        (6, ["JUDGMENT"]),
        (8, ["MECHANICAL"]),
        (13, ["JUDGMENT"]),
    ]


def test_multi_line_bullet_text_includes_its_continuation_lines():
    found = detect_bullets.detect_bullets(AGENT)
    assert (
        found[1].text
        == "- Multi-line check that\n  wraps onto a second line. [JUDGMENT]"
    )


def test_nested_bullet_is_part_of_its_parent_not_a_separate_bullet():
    found = detect_bullets.detect_bullets(AGENT)
    assert found[2].text == "- Parent check\n  - nested detail [MECHANICAL]"


def test_detect_section_running_to_end_of_file_is_parsed():
    assert [
        b.text for b in detect_bullets.detect_bullets("## Detect\n- only [JUDGMENT]\n")
    ] == ["- only [JUDGMENT]"]


def test_text_without_a_detect_section_yields_no_bullets():
    assert (
        detect_bullets.detect_bullets(
            "# Agent\n\n## Output\n\n- not detect [MECHANICAL]\n"
        )
        == []
    )


def test_detect_heading_with_a_suffix_is_not_the_detect_section():
    assert (
        detect_bullets.detect_bullets("## Detection Patterns\n- x [MECHANICAL]\n") == []
    )
