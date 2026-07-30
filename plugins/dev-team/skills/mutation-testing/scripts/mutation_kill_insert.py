#!/usr/bin/env python3
"""mutation_kill_insert.py — C# test-method insertion mechanics.

Split out of ``mutation_kill_loop.py`` (#1562): detect-or-refuse insertion of
generated test methods before a test class's closing brace. The heuristic
supports only conventional block-namespace, 4-space-indented C# test classes
— a file-scoped namespace or non-4-space indentation is refused rather than
risk a mis-insertion.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class InsertionRefused(Exception):
    """Raised when the class-closing brace can't be located safely.

    The insert heuristic only supports conventional block-namespace,
    4-space-indented C# test classes. For a file-scoped namespace (no wrapping
    braces) or non-4-space indentation, the loop refuses rather than append
    into a structurally wrong location.
    """


@dataclass(frozen=True)
class InsertOutcome:
    """Result of attempting to apply generated methods. ``inserted`` is False
    when the file was left untouched; ``reason`` says why."""

    inserted: bool
    reason: str


# Matches a public test-method declaration (async Task or void), capturing the
# method name. Framework-agnostic — no attribute or library name is assumed.
_METHOD_RE = re.compile(
    r"public\s+(?:async\s+)?(?:void|Task(?:<[^>]*>)?)\s+(\w+)\s*\("
)

# A file-scoped namespace declaration ends with a semicolon and has no
# wrapping braces: ``namespace Foo.Bar;``
_FILE_SCOPED_NS_RE = re.compile(r"^\s*namespace\s+[\w.]+\s*;", re.MULTILINE)


def detect_duplicate_methods(test_text: str, new_text: str) -> list[str]:
    """Return the method names in ``new_text`` that already exist in the file."""
    existing = set(_METHOD_RE.findall(test_text))
    incoming = _METHOD_RE.findall(new_text)
    return [name for name in incoming if name in existing]


def count_methods(new_text: str) -> int:
    """Count public test-method declarations in ``new_text``."""
    return len(_METHOD_RE.findall(new_text))


def _find_block_namespace_class_close(lines: Sequence[str]) -> int | None:
    """Return the index of the class-closing brace, or None to refuse.

    Walks from the end: finds the namespace-closing brace (a line whose
    stripped form is ``}``), then the last line that is exactly four spaces
    followed by ``}`` before it — the conventional block-namespace class
    close. Any other indentation yields None (refuse).
    """
    ns_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}":
            ns_idx = i
            break
    if ns_idx is None:
        return None
    for i in range(ns_idx - 1, -1, -1):
        if lines[i].rstrip("\r\n") == "    }":
            return i
    return None


def insert_before_class_close(test_file: Path, new_methods: str) -> None:
    """Insert ``new_methods`` before the test class's closing brace.

    Raises :class:`InsertionRefused` for a file-scoped namespace or any
    non-4-space-indented class the heuristic can't safely locate. The file is
    left untouched on refusal.
    """
    text = test_file.read_text(encoding="utf-8")
    if _FILE_SCOPED_NS_RE.search(text):
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: file-scoped namespace "
            "detected — the class-close heuristic supports only block-namespace, "
            "4-space-indented classes"
        )

    lines = text.splitlines(keepends=True)
    cc_idx = _find_block_namespace_class_close(lines)
    if cc_idx is None:
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: could not locate a "
            "conventional 4-space class-closing brace (non-standard indentation?)"
        )

    block = (
        ["\n"]
        + [ln if ln.endswith("\n") else ln + "\n" for ln in new_methods.strip().splitlines()]
        + ["\n"]
    )
    lines = lines[:cc_idx] + block + lines[cc_idx:]
    test_file.write_text("".join(lines), encoding="utf-8")


def apply_generated_methods(test_file: Path, new_methods: str) -> InsertOutcome:
    """Insert generated methods, guarding duplicates and unsafe structure.

    Returns an :class:`InsertOutcome`; the file is only ever written on the
    ``inserted=True`` path. Empty generation, duplicate method names, and a
    refused insert all leave the file untouched.
    """
    if not new_methods.strip():
        return InsertOutcome(False, "no methods generated")

    dupes = detect_duplicate_methods(test_file.read_text(encoding="utf-8"), new_methods)
    if dupes:
        return InsertOutcome(False, f"duplicate method names: {dupes}")

    try:
        insert_before_class_close(test_file, new_methods)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")
