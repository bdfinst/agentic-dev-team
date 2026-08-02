"""Content contract for knowledge/agent-review-methodology.md — the shared
3-phase Enumerate -> Classify -> Group review methodology extracted from
correctness-review.md's and naming-review.md's duplicated Protocol prose
(issue #1696).

Semantic correctness (whether a citing agent actually follows the
methodology) is verified by eval fixtures and real usage, not by grep —
these assertions verify the required headings and rationale phrases are
present and durable, per the existing
`tests/knowledge/test_adversarial_review_protocol_evidence.py` pattern.
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "agent-review-methodology.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_agent_review_methodology_md_exists() -> None:
    assert DOC.is_file()


def test_enumerate_heading_present(text: str) -> None:
    assert "## Enumerate" in text


def test_classify_heading_present(text: str) -> None:
    assert "## Classify" in text


def test_group_heading_present(text: str) -> None:
    assert "## Group" in text


def test_prevents_selective_attention_phrase_present(text: str) -> None:
    assert "prevents selective attention" in text


def test_anchors_before_applying_judgment_phrase_present(text: str) -> None:
    assert "anchors" in text
    assert "before applying judgment" in text


def test_proportional_to_distinct_problems_phrase_present(text: str) -> None:
    assert "proportional to the number of distinct problems" in text
