"""Content contract for knowledge/adversarial-review-protocol.md's Evidence
challenge (item 2 of The Loop), strengthened for #1342.

Three review agents (doc-review x2, token-efficiency-review x1), across one
build session, each made a confident, specific, checkable claim that was
false under direct verification:

  1. doc-review flagged a scope-mismatched agent count (an ADR's fleet-wide,
     3-plugin count vs. agent-registry.md tables that have only ever covered
     plugins/dev-team/agents/) as an inconsistency — no inconsistency existed
     once scope was accounted for.
  2. token-efficiency-review fabricated a file-content claim (quoted exact
     line numbers/content from orchestrator.md that didn't match) — the
     claim conflated orchestrator.md with a different file in the same
     review batch (qa-engineer.md).

(A third instance — an MCP wildcard tool-grant claim — is tracked and fixed
separately as #1340, which touches doc-review.md, not this file.)

Both surviving instances share one root cause: the shared Evidence challenge
only required a finding to quote content, not that the quote was freshly
re-verified against the *exact* named file/source immediately before citing,
and comparative claims were not required to confirm scope parity. This test
guards the strengthened wording that closes both gaps.

Semantic correctness (whether an agent actually follows the strengthened
wording) is verified by eval fixtures and real usage, not by grep — these
assertions verify the wording is present and durable, per the existing
`tests/knowledge/test_test_review_division_of_labor.py` pattern.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "adversarial-review-protocol.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_adversarial_review_protocol_md_exists() -> None:
    assert DOC.is_file()


# --- Pre-existing structure (regression guards) ---


def test_the_loop_heading_survives(text: str) -> None:
    assert "## The Loop" in text


def test_evidence_item_survives(text: str) -> None:
    assert re.search(r"\*\*Evidence\*\*", text)


def test_falsifiability_item_survives(text: str) -> None:
    assert re.search(r"\*\*Falsifiability\*\*", text)


def test_output_section_survives(text: str) -> None:
    assert "## Output" in text


# --- Strengthened Evidence requirements (#1342) ---


def test_evidence_requires_the_exact_named_file(text: str) -> None:
    assert re.search(r"exact named file", text, re.IGNORECASE)


def test_evidence_requires_verification_during_this_pass_not_memory(
    text: str,
) -> None:
    assert re.search(r"during this pass", text, re.IGNORECASE)
    assert re.search(r"\bmemory\b", text, re.IGNORECASE)


def test_evidence_calls_out_batch_review_file_identity_conflation(
    text: str,
) -> None:
    # Closes instance 3 (token-efficiency-review conflating orchestrator.md
    # with qa-engineer.md mid-batch): the wording must explicitly name
    # batch review of similarly-shaped files as the risk case, and require
    # re-opening the specific file immediately before citing it.
    assert re.search(r"batch review", text, re.IGNORECASE)
    assert re.search(r"similarly-shaped", text, re.IGNORECASE)
    assert re.search(r"immediately before citing", text, re.IGNORECASE)


def test_evidence_requires_scope_parity_for_comparative_claims(text: str) -> None:
    # Closes instance 2 (doc-review's scope-mismatched agent count): a claim
    # comparing counts/content across two sources must confirm both sources
    # cover the same scope before it is reported as an inconsistency.
    assert re.search(r"same scope", text, re.IGNORECASE)
    assert re.search(r"not an inconsistency", text, re.IGNORECASE)


def test_confidence_rubric_high_bar_matches_strengthened_evidence_item(
    text: str,
) -> None:
    # The Output section's confidence rubric must name the same
    # freshly-verified-citation standard as the Evidence item, so the two
    # don't drift out of sync.
    high_bullet = re.search(r"\*\*High\*\*:.*", text)
    assert high_bullet is not None
    assert re.search(r"freshly verified", high_bullet.group(0), re.IGNORECASE)
