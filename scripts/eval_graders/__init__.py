"""Pluggable grader registry (issue #309).

`scripts/eval_grade.py` used to be a monolith with inline branching for every
fixture genre. This package extracts the grading rules behind a registry keyed
by a `grader` field in `evals/expected/*.json`. A new fixture genre is now one
module plus one entry in ``REGISTRY`` — no edits to existing graders and no new
branches in the orchestration loop.

Contract for a grader callable::

    grade(spec: dict, actual: dict) -> list[str]

It returns a list of human-readable check-failure strings; an empty list means
PASS. ``spec`` is the per-entry expected JSON, ``actual`` is the recorded output
for that pair.

Backwards compatibility: entries in an expected file's ``agents`` block default
to the ``verdict`` grader and entries in its ``skills`` block default to
``skill_gate`` (see ``DEFAULT_GRADERS``), so every pre-registry fixture grades
byte-for-byte identically without declaring a ``grader`` field.
"""

from __future__ import annotations

from .skill_gate import grade_skill_gate
from .verdict import grade_verdict

# grader name -> grading callable. Adding a grader = one module + one entry here.
REGISTRY = {
    "verdict": grade_verdict,
    "skill_gate": grade_skill_gate,
}

# Default grader per expected-JSON block, preserving pre-registry behaviour.
DEFAULT_GRADERS = {"agents": "verdict", "skills": "skill_gate"}


def get_grader(name: str):
    """Return the grading callable for ``name``, or ``None`` if unregistered."""
    return REGISTRY.get(name)


def is_registered(name: str) -> bool:
    """True when ``name`` is a known grader."""
    return name in REGISTRY


def registered_graders() -> list[str]:
    """Sorted list of known grader names (for error messages / diagnostics)."""
    return sorted(REGISTRY)
