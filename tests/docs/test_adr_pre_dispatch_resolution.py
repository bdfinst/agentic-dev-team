"""ADR documenting pre-dispatch model routing decisions exists with the
required sections (historical record — superseded by ADR 0026; ADR 0004
itself is preserved verbatim, per docs/adr/README.md's supersession
convention).

Ported from tests/docs/adr_pre_dispatch_resolution_test.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

# The ADR slot is 0004 (0001-0003 are taken). The filename is fixed for this
# test; if a future contributor renumbers, update it here too.
ADR = REPO_ROOT / "docs" / "adr" / "0004-pre-dispatch-model-resolution.md"


@pytest.fixture(scope="module")
def adr_text() -> str:
    return ADR.read_text(encoding="utf-8")


def test_adr_file_exists() -> None:
    assert ADR.is_file()


def test_adr_contains_standard_sections(adr_text: str) -> None:
    assert re.search(r"^## Status", adr_text, re.MULTILINE)
    assert re.search(r"^## Context", adr_text, re.MULTILINE)
    assert re.search(r"^## Decision", adr_text, re.MULTILINE)
    assert re.search(r"^## Consequences", adr_text, re.MULTILINE)


def test_adr_decision_rejects_runtime_model_not_available_retry(
    adr_text: str,
) -> None:
    # Two anchors: the rejection itself and the rationale.
    assert "model_not_available" in adr_text.lower()
    assert "harness owns the dispatch" in adr_text.lower()


def test_adr_decision_records_pretooluse_hook_vs_orchestrator_instruction(
    adr_text: str,
) -> None:
    assert "pretooluse" in adr_text.lower()
    assert "orchestrator instruction" in adr_text.lower()
