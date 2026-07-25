"""Structural invariant: /test-improve's `### Phase N` headers appear in the
declared execution-order sequence, not phase-identity order (issue #1422).

Phase identities keep their historical numbers (Phase 1 = Analyze, Phase 2 =
Baseline, Phase 3 = Derive Gherkin, ...); only the *document/execution* order
changed so Baseline and Derive-Gherkin land before Analyze. This is a
structural scan of the raw SKILL.md — distinct from the banner-text and
gate-text content-guards in test_improve_phase_0.py/_1.py/_3.py — so a future
edit that silently re-reorders the blocks (or adds a phase) fails a test
rather than only being caught by manual re-reading.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"

# The declared execution order (issue #1422): 0 -> 2 -> 3 -> 1 -> 4 -> 5 ->
# 6 -> 7 -> 8 -> 9. Phase identities are unchanged; only this document order
# (which the orchestrator follows literally, per "## Steps") changed.
EXPECTED_ORDER = ["0", "2", "3", "1", "4", "5", "6", "7", "8", "9"]

_PHASE_HEADER_RE = re.compile(r"^### Phase (\d+)\b", re.MULTILINE)


def _text() -> str:
    return SKILL.read_text()


def _phase_header_sequence() -> list[str]:
    return _PHASE_HEADER_RE.findall(_text())


def test_all_ten_phase_headers_are_present_exactly_once():
    sequence = _phase_header_sequence()
    assert sorted(sequence, key=int) == sorted(EXPECTED_ORDER, key=int)
    assert len(sequence) == len(set(sequence))


def test_phase_headers_appear_in_the_declared_execution_order():
    """A future edit that silently re-reorders the Phase 0-4 blocks (or any
    other phase block) fails here, rather than only being caught by manual
    re-reading of the reordered region."""
    assert _phase_header_sequence() == EXPECTED_ORDER
