"""Contract tests for the sentence helpers in `_agent_text_helpers`."""

from __future__ import annotations

import pytest
from _agent_text_helpers import has_sentence_with_all, sentence_containing, sentences

BLOCK = """The critic reads the plan and
lists every scenario. It never runs the script.
Each finding names a slice. Each finding names a slice again."""


def test_sentences_collapses_line_wraps():
    assert sentences(BLOCK) == [
        "The critic reads the plan and lists every scenario.",
        "It never runs the script.",
        "Each finding names a slice.",
        "Each finding names a slice again.",
    ]


def test_has_sentence_with_all_is_true_for_two_terms_in_one_sentence():
    assert has_sentence_with_all(BLOCK, "reads the plan", "every scenario")


def test_has_sentence_with_all_is_false_for_terms_in_different_sentences():
    assert not has_sentence_with_all(BLOCK, "reads the plan", "never runs")


def test_sentence_containing_returns_the_single_hit():
    assert sentence_containing(BLOCK, "never runs") == "It never runs the script."


def test_sentence_containing_raises_on_zero_hits():
    with pytest.raises(AssertionError):
        sentence_containing(BLOCK, "absent term")


def test_sentence_containing_raises_on_two_hits():
    with pytest.raises(AssertionError):
        sentence_containing(BLOCK, "names a slice")
