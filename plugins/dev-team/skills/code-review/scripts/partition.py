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
import re

# Slice ids are zero-padded to this width so lexical and numeric order agree
# for the common case and artifact filenames sort naturally.
_ID_WIDTH = 4

# Path/name tokens that positively signal a declarative artifact (interface,
# type, DTO, constant, model, schema, enum definitions).
_DECLARATIVE_TOKENS = {
    "model", "models", "dto", "dtos", "type", "types", "interface",
    "interfaces", "constant", "constants", "schema", "schemas", "enum",
    "enums",
}

# Tokens that signal executable behavior. Their presence disqualifies a file
# from being declarative even if a declarative token also matches — this keeps
# the classifier conservative (a mislabel can only ever add a heavier panel,
# never drop below the safe full panel).
_BEHAVIORAL_TOKENS = {
    "service", "services", "controller", "controllers", "handler", "handlers",
    "component", "components", "hook", "hooks", "util", "utils", "helper",
    "helpers", "middleware", "reducer", "reducers", "saga", "sagas",
    "resolver", "resolvers",
}


def _path_tokens(path: str) -> set[str]:
    """Return the lowercased word tokens of every segment of ``path``.

    Both directory segments and the filename are word-tokenized on ``. _ -`` so
    a behavioral token is caught wherever it appears — a compound suffix like
    ``user.service.ts`` **and** a compound directory like ``order-service/``
    both yield ``service``. Tokenizing only the filename would silently drop a
    behavioral token hidden in a directory name (a false-declarative in the
    unsafe direction). The trailing filename extension is dropped first.
    """
    lower = path.lower()
    segments = re.split(r"[\\/]", lower)
    parts = segments[-1].split(".")
    name_parts = parts[:-1] if len(parts) > 1 else parts
    raw_tokens = list(segments[:-1]) + name_parts
    words: set[str] = set()
    for token in raw_tokens:
        words |= set(re.split(r"[._\-]", token))
    return words


def _is_declarative_file(path: str) -> bool:
    """Return True when ``path`` looks like a pure declarative artifact.

    Name/extension heuristic only (pure). TypeScript declaration files
    (``.d.ts``) are always declarative. Otherwise a file qualifies only when a
    declarative token matches and no behavioral token does.
    """
    if path.lower().endswith(".d.ts"):
        return True
    tokens = _path_tokens(path)
    if tokens & _BEHAVIORAL_TOKENS:
        return False
    return bool(tokens & _DECLARATIVE_TOKENS)


def is_declarative_slice(files: list[str]) -> bool:
    """Return True only when *every* file in the slice is declarative.

    An empty slice is not declarative (nothing to assert). Conservative by
    design: any file that is not clearly declarative makes the whole slice
    non-declarative, so it keeps the full review panel.
    """
    if not files:
        return False
    return all(_is_declarative_file(f) for f in files)


def _slice_id(index: int) -> str:
    """Return the stable, zero-padded id for the ``index``-th slice (1-based)."""
    return str(index).zfill(_ID_WIDTH)


def _append_slice(slices: list[dict], files: list[str]) -> None:
    """Append one slice record to ``slices`` with the next sequential id.

    Single home for the slice-record shape so both emit paths (sibling flush
    and oversized-directory chunking) stay in lockstep if the shape changes.
    The ``is_declarative`` flag drives the reduced review panel (Slice 2).
    """
    file_list = list(files)
    slices.append(
        {
            "id": _slice_id(len(slices) + 1),
            "files": file_list,
            "is_declarative": is_declarative_slice(file_list),
        }
    )


def _group_by_directory(files: list[str]) -> dict[str, list[str]]:
    """Group ``files`` by parent directory, each group's files sorted.

    The returned dict is ordered by directory name so downstream packing is
    deterministic.
    """
    groups: dict[str, list[str]] = {}
    for path in files:
        directory = os.path.dirname(path)
        groups.setdefault(directory, []).append(path)
    return {d: sorted(groups[d]) for d in sorted(groups)}


def partition_files(files: list[str], cap: int) -> list[dict]:
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

    slices: list[dict] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            _append_slice(slices, current)
            current.clear()

    for dir_files in grouped.values():
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
