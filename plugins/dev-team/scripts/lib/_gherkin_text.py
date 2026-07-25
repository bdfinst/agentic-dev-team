"""_gherkin_text.py — line-level Gherkin text primitives shared across the
`.feature`-file scripts (gherkin_feature_merge.py, gherkin_failure_path_gate.py).

Hoisted out after `_stripped()` and the `Feature:`/`Scenario:`/`Scenario
Outline:` prefix constants were found duplicated byte-for-byte between the two
scripts (issue #1420 code-review follow-up) — the same "third occurrence"
threshold `_vendored_tree.py` was extracted at.

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

FEATURE_PREFIX = "Feature:"
SCENARIO_OUTLINE_PREFIX = "Scenario Outline:"
SCENARIO_PREFIX = "Scenario:"


def stripped(line: str) -> str:
    """Strip only the line ending, preserving all other whitespace — so a
    caller reconstructing text from `splitlines(keepends=True)` output stays
    byte-exact for everything except the ending itself."""
    return line.rstrip("\r\n")
