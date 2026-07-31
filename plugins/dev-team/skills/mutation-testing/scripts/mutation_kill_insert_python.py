#!/usr/bin/env python3
"""mutation_kill_insert_python.py — Python/pytest test-function insertion
mechanics.

Split out of ``mutation_kill_loop_python.py`` (#1583), mirroring the C#
split ``mutation_kill_insert.py`` (#1562): detect-or-refuse insertion of
generated pytest test functions at the end of a test file. Unlike C#'s
"find the class-closing brace" problem, a flat pytest module has no
enclosing structure to locate — the safe insertion point is simply
end-of-file, PROVIDED the file already follows that flat, top-level
``def test_*():`` convention. A file with no top-level ``def test_`` function
at all (e.g. tests organized as ``class Test...:`` methods) doesn't match
this convention, and the loop refuses rather than guess.

``InsertOutcome``/``InsertionRefused`` are imported from
``mutation_kill_shared`` (relocated from ``mutation_safety_gate`` in #1602;
not defined here) — they're structurally identical to the C# sibling's, so
both modules share one definition instead of two hand-maintained copies. See
``mutation_kill_shared``'s module docstring for the unification rationale.
"""

from __future__ import annotations

import re
from pathlib import Path

import mutation_safety_gate
from mutation_kill_shared import InsertionRefused, InsertOutcome

# A top-level (unindented) pytest test function declaration, capturing the name.
_FUNC_RE = re.compile(r"^def\s+(test_\w+)\s*\(", re.MULTILINE)


def detect_duplicate_functions(test_text: str, new_text: str) -> list[str]:
    """Return the function names in ``new_text`` that already exist in the file."""
    existing = set(_FUNC_RE.findall(test_text))
    incoming = _FUNC_RE.findall(new_text)
    return [name for name in incoming if name in existing]


def count_tests(new_text: str) -> int:
    """Count top-level ``def test_*():`` declarations in ``new_text``.

    Mirrors ``mutation_kill_insert.count_methods`` — the loop uses this to
    report how many new tests a round added in its commit message.
    """
    return len(_FUNC_RE.findall(new_text))


def append_at_end_of_file(test_file: Path, new_tests: str, text: str) -> None:
    """Append ``new_tests`` to the end of the file, with one blank line of
    separation, and a trailing newline.

    Raises :class:`InsertionRefused` when the file has no existing top-level
    ``def test_*():`` — the flat-module convention this heuristic supports.
    The file is left untouched on refusal.

    ``text`` is the current test-file content, already read by the caller
    (:func:`apply_generated_tests`) — this function performs no read of its
    own, so freshness is entirely the caller's responsibility.
    """
    if not _FUNC_RE.search(text):
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: no top-level "
            "`def test_*():` found — this heuristic supports only the flat "
            "module convention (a class-based test file needs a different "
            "insertion point, not appended at end-of-file)"
        )

    body = new_tests.strip()
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    test_file.write_text(text + separator + body + "\n", encoding="utf-8")


# A deny-list of APIs a test function that merely kills mutants never
# legitimately needs. Scoped to generated *test* text only — never to the
# source-under-test. Same rationale and same category names as
# ``mutation_kill_insert``'s C# counterpart (kept consistent as a stable,
# operator-facing and test-pinned contract) — this is the Python/pytest
# equivalent, guarding this loop's own ``--headless`` unattended-commit path
# against a prompt-injection payload in the mutated source producing
# generated test code with network/filesystem/process side effects that
# would still pass compile+test and get committed with zero human review.
_UNSAFE_PATTERNS: dict[str, re.Pattern[str]] = {
    "network": re.compile(
        r"\b(requests\s*\.|urllib\s*\.\s*request|urllib3\s*\.|httpx\s*\.|socket\s*\.|http\s*\.\s*client)\b"
    ),
    "process": re.compile(
        r"\b(subprocess\s*\.|os\s*\.\s*system|os\s*\.\s*popen|os\s*\.\s*exec\w*|"
        r"os\s*\.\s*(spawn\w*|posix_spawn|fork|forkpty)|Popen)\b"
    ),
    "filesystem": re.compile(
        r"\b(shutil\s*\.\s*rmtree|os\s*\.\s*(remove|unlink))\b"
        r"|\.\s*(write_text|write_bytes|unlink)\s*\("
        r"|open\s*\([^)]*[\"'][waxA]"
    ),
    "environment": re.compile(r"\b(os\s*\.\s*environ|os\s*\.\s*getenv)\b"),
    "reflection": re.compile(r"\b(importlib\s*\.\s*import_module|__import__)\b"),
    "interop": re.compile(r"\b(eval|exec)\s*\(|\bctypes\s*\.|\bpickle\s*\.\s*loads\s*\("),
}


def scan_for_unsafe_patterns(new_tests: str) -> list[str]:
    """Return the category names of any unsafe pattern found in generated text.

    A non-empty result refuses insertion outright — this deny-list is
    deliberately conservative for *generated test* code specifically (a
    legitimate mutant-killing test never needs network/filesystem/process/env
    access), so a false positive refuses-and-logs rather than silently
    inserting unreviewed code. Delegates to :mod:`mutation_safety_gate`,
    shared with :mod:`mutation_kill_insert`, so a future bypass fix or new
    category lands once for both languages.
    """
    return mutation_safety_gate.scan_for_unsafe_patterns(new_tests, _UNSAFE_PATTERNS)


def apply_generated_tests(test_file: Path, new_tests: str) -> InsertOutcome:
    """Insert generated tests, guarding duplicates and unsafe structure.

    Returns an :class:`InsertOutcome`; the file is only ever written on the
    ``inserted=True`` path. Empty generation, an unsafe pattern, duplicate
    function names, and a refused insert all leave the file untouched.

    Reads ``test_file`` exactly once here — immediately before the
    duplicate-name check — and reuses that single fresh read for both the
    check and the write (passed through to :func:`append_at_end_of_file`,
    which performs no read of its own). Reading fresh here, after the
    caller's (possibly multi-minute) generation call has already returned,
    means a test function added to the file externally in the meantime is
    still caught as a duplicate rather than silently double-inserted
    (#1598/#1584 review, item 7).
    """
    if not new_tests.strip():
        return InsertOutcome(False, "no tests generated")

    unsafe_categories = scan_for_unsafe_patterns(new_tests)
    if unsafe_categories:
        return InsertOutcome(False, f"refused — unsafe pattern(s): {unsafe_categories}")

    text = test_file.read_text(encoding="utf-8")

    dupes = detect_duplicate_functions(text, new_tests)
    if dupes:
        return InsertOutcome(False, f"duplicate function names: {dupes}")

    try:
        append_at_end_of_file(test_file, new_tests, text)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")
