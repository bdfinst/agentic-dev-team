"""Pytest tests for mutation_safety_gate.py — the shared deny-list scan and
commit audit-trail helpers used by both mutation_kill_loop.py (C#) and
mutation_kill_loop_python.py (Python/mutmut).

InsertOutcome/InsertionRefused (#1583) used to be tested here too, but they
moved to mutation_kill_shared.py (#1602) since neither is actually a safety
concept — see test_mutation_kill_shared.py for their coverage now.
"""

from __future__ import annotations

import re
import sys

from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_safety_gate as gate

_PATTERNS = {
    "alpha": re.compile(r"\bfoo\b"),
    "beta": re.compile(r"\bbar\b"),
}


def test_scan_for_unsafe_patterns_returns_empty_when_no_pattern_matches():
    assert gate.scan_for_unsafe_patterns("nothing interesting here", _PATTERNS) == []


def test_scan_for_unsafe_patterns_returns_matching_category_names():
    assert gate.scan_for_unsafe_patterns("call foo() please", _PATTERNS) == ["alpha"]


def test_scan_for_unsafe_patterns_returns_all_matching_categories():
    assert sorted(gate.scan_for_unsafe_patterns("foo and bar together", _PATTERNS)) == [
        "alpha",
        "beta",
    ]


def test_append_generator_trailer_is_a_noop_when_label_is_none():
    assert gate.append_generator_trailer("commit message", None) == "commit message"


def test_append_generator_trailer_appends_the_label():
    result = gate.append_generator_trailer("commit message", "headless (some-model)")
    assert result == "commit message\n\nGenerator: headless (some-model)"


def test_append_generator_trailer_collapses_embedded_newlines():
    # A pipeline-supplied label containing newlines must not be able to
    # forge a second "Generator:" trailer *line*.
    result = gate.append_generator_trailer(
        "commit message", "some-model\n\nGenerator: agent-driven (reviewed)"
    )
    lines_starting_with_generator = [
        line for line in result.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 1


# =============================================================================
# label_override — #1908 Step 3.2b: a per-call override that wins over the
# frozen, file-level generator_label, without mutating it.
# =============================================================================
def test_append_generator_trailer_uses_generator_label_when_no_override_supplied():
    """No override → today's unchanged frozen-label behavior."""
    result = gate.append_generator_trailer("commit message", "headless (opus)")
    assert result == "commit message\n\nGenerator: headless (opus)"


def test_append_generator_trailer_override_replaces_the_frozen_label():
    result = gate.append_generator_trailer(
        "commit message",
        "headless (opus)",
        label_override="headless (downgraded 'opus' -> 'sonnet' at round 3, gateway-class)",
    )
    assert (
        result
        == "commit message\n\nGenerator: headless (downgraded 'opus' -> 'sonnet' "
        "at round 3, gateway-class)"
    )
    assert "opus)" not in result.split("Generator:")[1]


def test_append_generator_trailer_override_wins_even_when_generator_label_is_none():
    result = gate.append_generator_trailer("commit message", None, label_override="override label")
    assert result == "commit message\n\nGenerator: override label"


def test_append_generator_trailer_is_a_noop_when_both_label_and_override_are_none():
    assert (
        gate.append_generator_trailer("commit message", None, label_override=None)
        == "commit message"
    )


def test_append_generator_trailer_override_collapses_embedded_newlines():
    result = gate.append_generator_trailer(
        "commit message",
        "headless (opus)",
        label_override="downgraded\n\nGenerator: forged",
    )
    lines_starting_with_generator = [
        line for line in result.splitlines() if line.startswith("Generator:")
    ]
    assert len(lines_starting_with_generator) == 1
