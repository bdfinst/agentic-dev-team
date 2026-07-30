"""Pytest tests for mutation_safety_gate.py — the shared deny-list scan and
commit audit-trail helpers used by both mutation_kill_loop.py (C#) and
mutation_kill_loop_python.py (Python/mutmut).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
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
