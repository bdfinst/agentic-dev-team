#!/usr/bin/env python3
"""Partition a review's file list into bounded, module-aligned slices.

The public entry point is :func:`partition_files`. It is a **pure function** —
no filesystem access, no globals, no clock — so it is exercised directly from
``tests/scripts/test_partition.py``. ``sliced-mode.md`` orchestrates the review
around the slices this returns; ``ledger.py`` persists them.

Slicing rules (mirrors the plan's Slice 1 Gherkin):

- Files are grouped by their parent directory (the module boundary).
- Directories are visited in sorted order for determinism.
- A directory holding more than ``cap`` files is split across consecutive
  slices, none exceeding ``cap``.
- Small sibling directories are coalesced together into a slice up to ``cap``.
- Slice ids are stable, zero-padded, sequential strings, so the same input
  always yields the same ids mapped to the same files in the same order.
"""

from __future__ import annotations

import os
from typing import Dict, List

# Slice ids are zero-padded to this width so lexical and numeric order agree
# for the common case and artifact filenames sort naturally.
_ID_WIDTH = 4


def _slice_id(index: int) -> str:
    """Return the stable, zero-padded id for the ``index``-th slice (1-based)."""
    return str(index).zfill(_ID_WIDTH)


def _append_slice(slices: List[dict], files: List[str]) -> None:
    """Append one slice record to ``slices`` with the next sequential id.

    Single home for the slice-record shape so both emit paths (sibling flush
    and oversized-directory chunking) stay in lockstep if the shape changes.
    """
    slices.append({"id": _slice_id(len(slices) + 1), "files": list(files)})


def _group_by_directory(files: List[str]) -> "Dict[str, List[str]]":
    """Group ``files`` by parent directory, each group's files sorted.

    The returned dict is ordered by directory name so downstream packing is
    deterministic.
    """
    groups: Dict[str, List[str]] = {}
    for path in files:
        directory = os.path.dirname(path)
        groups.setdefault(directory, []).append(path)
    return {d: sorted(groups[d]) for d in sorted(groups)}


def partition_files(files: List[str], cap: int) -> List[dict]:
    """Partition ``files`` into module-aligned slices of at most ``cap`` files.

    Returns an ordered list of slice records ``{"id": str, "files": [str]}``.
    An empty ``files`` yields ``[]``; a single file yields exactly one slice.

    Raises ``ValueError`` if ``cap`` is not a positive integer — the caller
    (``activation.should_slice``) validates ``--slice`` before reaching here,
    but the pure function guards its own contract too.
    """
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ValueError(f"cap must be a positive integer, got {cap!r}")

    grouped = _group_by_directory(files)

    slices: List[dict] = []
    current: List[str] = []

    def flush() -> None:
        if current:
            _append_slice(slices, current)
            current.clear()

    for _directory, dir_files in grouped.items():
        if len(dir_files) > cap:
            # Oversized directory: flush whatever small siblings accumulated,
            # then emit the directory in cap-sized chunks of its own.
            flush()
            for start in range(0, len(dir_files), cap):
                _append_slice(slices, dir_files[start : start + cap])
            continue

        if len(current) + len(dir_files) > cap:
            flush()
        current.extend(dir_files)

    flush()
    return slices
