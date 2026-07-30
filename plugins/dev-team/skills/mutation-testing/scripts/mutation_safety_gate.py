#!/usr/bin/env python3
"""mutation_safety_gate.py — shared deny-list scan and commit audit-trail
helpers for mutation_kill_loop.py and mutation_kill_loop_python.py.

Both loops share the same ``--headless`` unattended-commit architecture and
the same threat: a prompt-injection payload in the mutated source could
produce generated test code with side effects that pass build+test and get
committed with zero human review. Each loop supplies its own
language-specific deny-list of patterns; this module owns the single,
shared control flow around them (scan, refuse-on-match; sanitize, then
append an audit trailer) so a bypass fix or a new unsafe category lands
once for both languages instead of drifting between two hand-maintained
copies — a drift risk that fixing this exact vulnerability once already
demonstrated in practice.

Stdlib-only (``re``). Python 3.8+. See ADR 0014.
"""

from __future__ import annotations

import re


def scan_for_unsafe_patterns(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    """Return the category names of any unsafe pattern found in ``text``.

    A non-empty result refuses insertion outright — the caller's deny-list
    is deliberately conservative for *generated test* code specifically (a
    legitimate mutant-killing test never needs the categories a deny-list
    covers), so a false positive refuses-and-logs rather than silently
    inserting unreviewed code.
    """
    return [name for name, pattern in patterns.items() if pattern.search(text)]


def append_generator_trailer(message: str, generator_label: str | None) -> str:
    """Append a ``Generator: <label>`` audit-trail trailer to a commit message.

    Distinguishes an unattended, unreviewed commit (``--headless``) from an
    agent-driven one (a live turn with an operator present) without
    re-deriving it from CI logs. Whitespace in ``generator_label`` is
    collapsed so a pipeline-supplied value containing newlines can't forge
    an extra trailer line. A no-op when ``generator_label`` is ``None``.
    """
    if generator_label is None:
        return message
    return message + f"\n\nGenerator: {' '.join(generator_label.split())}"
