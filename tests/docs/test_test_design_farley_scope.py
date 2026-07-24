"""Regression guard for #533: Farley Score in /test-design must honor
--path / --since scope and label the score with the scope it was
computed over.

Ported from tests/docs/test_design_farley_scope_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "test-design" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(text: str) -> str:
    return text.replace("\n", " ")


def test_declares_unscoped_farley_score_label(text: str) -> None:
    assert "Farley Score (all tests)" in text


def test_declares_path_farley_score_label(text: str) -> None:
    assert "Farley Score (under" in text


def test_declares_since_farley_score_label(text: str) -> None:
    assert "Farley Score (changed since" in text


def test_declares_combined_path_and_since_label(text: str) -> None:
    # e.g. "Farley Score (under <dir>, changed since <ref>)"
    assert re.search(r"Farley Score \(under [^,)]+, changed since", text)


def test_documents_intersection_semantics_for_combined_scope(text: str) -> None:
    # Match specific phrases, not the bare word 'both' or 'and' which appear
    # in ordinary prose all over the SKILL.
    assert re.search(r"\bintersection\b|the intersection of both sets", text)


def test_declares_empty_scope_branch(text: str) -> None:
    assert "no in-scope test files" in text


def test_directs_step_3_to_reuse_step_1_resolved_file_set(text: str) -> None:
    assert re.search(
        r"set (already )?resolved in Step 1|reuse Step 1|already-resolved",
        text,
        re.IGNORECASE,
    )


def test_names_step_1_as_single_scope_resolution_authority(flat: str) -> None:
    # Collapse newlines before matching so a soft-wrapped phrase still hits.
    assert re.search(
        r"single\s+scope-resolution authority|one\s+scope-resolution authority",
        flat,
        re.IGNORECASE,
    )


def test_no_longer_claims_farley_independent_of_path_or_since(text: str) -> None:
    assert "This headline score is independent of" not in text


def test_no_longer_carries_whole_suite_stale_phrases(text: str) -> None:
    assert not re.search(
        r"score always reflects the full suite|Farley Score \(all existing tests\)",
        text,
    )
