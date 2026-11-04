"""Unit tests for the fence and frontmatter helpers in skill_doc_helpers
(added with test_doctor_skill, #2272)."""

from __future__ import annotations

import pytest
from skill_doc_helpers import fenced_blocks, frontmatter_fields

FENCE = "```"
WRAPPER = "````"


def _doc(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_two_blocks_of_the_tag_come_back_in_order():
    text = _doc(
        f"{FENCE}bash", "first", FENCE, "prose", f"{FENCE}bash", "second", FENCE
    )

    assert fenced_blocks(text, "bash") == ["first", "second"]


def test_a_block_with_another_tag_is_skipped():
    text = _doc(f"{FENCE}text", "no", FENCE, f"{FENCE}bash", "yes", FENCE)

    assert fenced_blocks(text, "bash") == ["yes"]


def test_an_untagged_block_is_skipped():
    text = _doc(FENCE, "no", FENCE)

    assert fenced_blocks(text, "bash") == []


def test_only_the_first_info_word_is_compared_to_the_tag():
    text = _doc(f"{FENCE}bash title=x", "yes", FENCE)

    assert fenced_blocks(text, "bash") == ["yes"]


def test_a_tag_that_merely_starts_with_the_tag_is_skipped():
    text = _doc(f"{FENCE}bashful", "no", FENCE)

    assert fenced_blocks(text, "bash") == []


def test_an_indented_fence_is_seen():
    text = _doc(f"  {FENCE}bash", "  yes", f"  {FENCE}")

    assert fenced_blocks(text, "bash") == ["  yes"]


def test_a_fence_indented_four_spaces_is_not_a_fence():
    text = _doc(f"    {FENCE}bash", "no", f"    {FENCE}")

    assert fenced_blocks(text, "bash") == []


def test_a_tilde_fence_is_seen():
    text = _doc("~~~bash", "yes", "~~~")

    assert fenced_blocks(text, "bash") == ["yes"]


def test_a_tilde_fence_does_not_close_on_backticks():
    text = _doc("~~~bash", "one", FENCE, "two", "~~~")

    assert fenced_blocks(text, "bash") == [f"one\n{FENCE}\ntwo"]


def test_a_four_backtick_wrapper_does_not_close_on_an_inner_three_backtick_fence():
    text = _doc(f"{WRAPPER}bash", f"{FENCE}text", "inner", FENCE, WRAPPER)

    assert fenced_blocks(text, "bash") == [f"{FENCE}text\ninner\n{FENCE}"]


def test_an_inner_same_length_fence_with_an_info_string_does_not_close_the_block():
    text = _doc(f"{FENCE}bash", "a", f"{FENCE}text", "b", FENCE)

    assert fenced_blocks(text, "bash") == [f"a\n{FENCE}text\nb"]


def test_a_longer_closing_fence_closes_the_block():
    text = _doc(f"{FENCE}bash", "x", WRAPPER)

    assert fenced_blocks(text, "bash") == ["x"]


def test_an_unclosed_block_yields_nothing():
    text = _doc(f"{FENCE}bash", "dangling")

    assert fenced_blocks(text, "bash") == []


def test_text_without_fence_lines_yields_nothing():
    assert fenced_blocks(_doc("just prose", "bash"), "bash") == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("name: doctor", "doctor"),
        ('argument-hint: "[--json] [--fix]"', "[--json] [--fix]"),
        ("user-invocable: true", "true"),
    ],
    ids=["plain", "quoted", "boolean-word"],
)
def test_frontmatter_fields_reads_a_single_line_value(line, expected):
    key = line.split(":")[0]

    assert frontmatter_fields(_doc("---", line, "---", "body"))[key] == expected


def test_frontmatter_fields_joins_a_folded_value_on_single_spaces():
    text = _doc(
        "---", "description: >-", "  first part", "  second part", "name: x", "---"
    )

    assert frontmatter_fields(text) == {
        "description": "first part second part",
        "name": "x",
    }


def test_frontmatter_fields_ignores_the_body():
    text = _doc("---", "name: x", "---", "other: y")

    assert frontmatter_fields(text) == {"name": "x"}
