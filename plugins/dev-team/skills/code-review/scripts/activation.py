#!/usr/bin/env python3
"""Decide whether a /code-review run should engage sliced mode, and at what cap.

Pure policy — no filesystem, no globals. ``should_slice`` encodes the flag /
scope / threshold precedence the plan's Slice 1 Gherkin specifies;
``check_slice_ceiling`` is the advisory guard for extreme-scale repos. Kept in
its own module (not ``partition.py``) so activation *policy* can change without
touching the partitioning *algorithm*.
"""

from __future__ import annotations

# Default per-slice file cap when sliced mode auto-engages (operator can
# override with --slice N).
DEFAULT_CAP = 50

# A full-repo review with more than this many files auto-engages sliced mode.
# Mirrors the existing ">500" scope-validation tier in code-review/SKILL.md.
LARGE_REPO_THRESHOLD = 500

# Above this many slices the run warns and suggests a larger cap. Advisory
# only — it never refuses (see the plan's Risks section).
SLICE_COUNT_CEILING = 200

# The one scope kind that auto-engages. --path / --since / auto-scoped
# uncommitted changes are never auto-sliced.
FULL_REPO = "full-repo"


def _validate_cap(value: object) -> int:
    """Return ``value`` as a positive int cap, or raise ValueError naming it."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"--slice must be a positive integer number of files per slice, "
            f"got {value!r}"
        )
    return value


def should_slice(
    scope_kind: str,
    file_count: int,
    *,
    threshold: int = LARGE_REPO_THRESHOLD,
    slice_flag: int | None = None,
    no_slice_flag: bool = False,
    default_cap: int = DEFAULT_CAP,
) -> tuple[bool, int | None]:
    """Return ``(engage_sliced_mode, effective_cap)``.

    Precedence (highest first):

    1. ``--no-slice`` always wins — never slice (returns ``(False, None)``).
    2. ``--slice N`` always slices with cap ``N`` at any size; ``N`` is
       validated as a positive integer (raises ``ValueError`` otherwise).
    3. Auto-engage only when ``scope_kind`` is full-repo **and**
       ``file_count`` is strictly greater than ``threshold``. Exactly at the
       threshold does not engage.
    4. Otherwise do not slice.
    """
    if no_slice_flag:
        return (False, None)

    if slice_flag is not None:
        return (True, _validate_cap(slice_flag))

    if scope_kind == FULL_REPO and file_count > threshold:
        return (True, default_cap)

    return (False, None)


def check_slice_ceiling(
    slice_count: int, ceiling: int = SLICE_COUNT_CEILING
) -> str | None:
    """Return an advisory warning when ``slice_count`` exceeds ``ceiling``.

    Advisory only — the caller reports it and proceeds; it never blocks. Returns
    ``None`` when the count is at or below the ceiling.
    """
    if slice_count > ceiling:
        return (
            f"Slice count is very high ({slice_count} slices). Consider a larger "
            f"--slice cap to reduce the number of agent panels and the run's cost."
        )
    return None
