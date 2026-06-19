"""The `skill_gate` grader (issue #309).

This is the original `grade_skill` path lifted verbatim out of the monolith: it
grades an advisory skill's recorded report (the `tlg-*` test-layer-gates corpus)
against its expected JSON — which gates fired, which pyramid layers were
recommended, and keyword presence/absence over the full report text. It is the
default grader for entries in an expected file's `skills` block.
"""

from __future__ import annotations

from ._common import mentions


def grade_skill_gate(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []
    got_gates = set(actual.get("gates", []) or [])
    for g in spec.get("expectedGates", []):
        if g not in got_gates:
            fails.append(f"gate: expected gate {g!r} to fire")
    got_layers = set(actual.get("layers", []) or [])
    for layer in spec.get("expectedLayers", []):
        if layer not in got_layers:
            fails.append(f"layer: expected layer {layer!r}")

    report = str(actual.get("report", ""))
    for kw in spec.get("mustMention", []):
        if not mentions(report, kw):
            fails.append(f"mustMention: missing {kw!r}")
    for kw in spec.get("mustNotMention", []):
        if mentions(report, kw):
            fails.append(f"mustNotMention: found forbidden {kw!r}")
    return fails
