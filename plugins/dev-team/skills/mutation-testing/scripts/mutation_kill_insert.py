#!/usr/bin/env python3
"""mutation_kill_insert.py — C# test-method insertion mechanics.

Split out of ``mutation_kill_loop.py`` (#1562): detect-or-refuse insertion of
generated test methods before a test class's closing brace. The heuristic
supports only conventional block-namespace, 4-space-indented C# test classes
— a file-scoped namespace or non-4-space indentation is refused rather than
risk a mis-insertion.

``InsertOutcome``/``InsertionRefused`` are imported from
``mutation_kill_shared`` (#1583, relocated from ``mutation_safety_gate`` in
#1602), not defined here — they're structurally identical to the Python
sibling's (``mutation_kill_insert_python.py``), so both modules share one
definition instead of two hand-maintained copies. See
``mutation_kill_shared``'s module docstring for the unification rationale.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import mutation_safety_gate
from mutation_kill_shared import InsertionRefused, InsertOutcome

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


# A deny-list of APIs a test method that merely kills mutants never
# legitimately needs. Scoped to generated *test* text only — never to the
# source-under-test — so it doesn't false-positive on production code that
# does real I/O. This is a static-pattern gate, not a sandbox: a
# sufficiently obfuscated payload (reflection-built names, string
# concatenation) could still evade it. Guards against a prompt-injection
# payload in the mutated source producing generated test code with
# network/filesystem/process side effects that would still pass build+test
# (which only check compilation and pass/fail, never behavior) and, in
# --headless mode, get committed with zero human review. Category names are
# a stable, test-pinned contract shared with mutation_kill_loop_python's
# deny-list — renaming one is a breaking change for callers matching on
# InsertOutcome.reason.
_UNSAFE_PATTERNS: dict[str, re.Pattern[str]] = {
    "network": re.compile(
        r"\b(HttpClient|WebRequest|WebClient|TcpClient|UdpClient|SmtpClient|Socket|Dns|"
        r"System\s*\.\s*Net\s*\.)\b"
    ),
    "process": re.compile(r"\b(Process|StartInfo|ProcessStartInfo)\b"),
    "filesystem": re.compile(
        r"\b(File\s*\.\s*(WriteAllText|WriteAllBytes|WriteAllLines|AppendAllText|"
        r"AppendAllLines)(Async)?|File\s*\.\s*(Create|Delete|Move|Copy|Open|OpenWrite)|"
        r"Directory\s*\.\s*(Delete|CreateDirectory|Move)|StreamWriter|FileStream|"
        r"FileInfo|DirectoryInfo)\b"
    ),
    "environment": re.compile(
        r"\b(Environment\s*\.\s*GetEnvironmentVariables?|ConfigurationManager\s*\.\s*AppSettings)\b"
    ),
    "reflection": re.compile(
        r"\b(Assembly\s*\.\s*Load(From|File|WithPartialName)?|"
        r"Activator\s*\.\s*CreateInstance(From)?|System\s*\.\s*Reflection\s*\.\s*Emit)\b"
    ),
    "interop": re.compile(r"\b(Marshal\s*\.|DllImport)\b|(?<![\w.])unsafe\b"),
}


def scan_for_unsafe_patterns(new_methods: str) -> list[str]:
    """Return the category names of any unsafe pattern found in generated text.

    A non-empty result refuses insertion outright — this deny-list is
    deliberately conservative for *generated test* code specifically (a
    legitimate mutant-killing test never needs network/filesystem/process/env
    access), so a false positive refuses-and-logs rather than silently
    inserting unreviewed code. Delegates to :mod:`mutation_safety_gate`,
    shared with :mod:`mutation_kill_insert_python`, so a future bypass fix or
    new category lands once for both languages.
    """
    return mutation_safety_gate.scan_for_unsafe_patterns(new_methods, _UNSAFE_PATTERNS)


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


def insert_before_class_close(test_file: Path, new_methods: str, text: str) -> None:
    """Insert ``new_methods`` before the test class's closing brace.

    Raises :class:`InsertionRefused` for a file-scoped namespace or any
    non-4-space-indented class the heuristic can't safely locate. The file is
    left untouched on refusal.

    ``text`` is the current test-file content, already read by the caller
    (:func:`apply_generated_methods`) — this function performs no read of its
    own. A previous, optional ``test_text=`` shape let a caller pass in
    content that bypassed reading the file's CURRENT state (including this
    function's own refusal-guard check running against stale content rather
    than what's actually on disk) — a real hazard even though no caller
    exploited it. Removing the optional/None-triggered-fallback shape closes
    that off: freshness is now entirely ``apply_generated_methods``'s
    responsibility, which reads immediately before calling this (#1598/#1584
    review, item 7).
    """
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
    ``inserted=True`` path. Empty generation, an unsafe pattern, duplicate
    method names, and a refused insert all leave the file untouched.

    Reads ``test_file`` exactly once here — immediately before the
    duplicate-name check — and reuses that single fresh read for both the
    check and the write (passed through to :func:`insert_before_class_close`,
    which performs no read of its own). A prior shape let the caller (e.g.
    ``_run_round``) thread in its OWN already-read ``test_text`` for the
    duplicate check — but that text was read *before* the possibly
    multi-minute ``generate()`` call, so the check ran against a stale
    snapshot: a method name added to the file during generation (by another
    process, or a second concurrent round) would go undetected as a
    duplicate. Reading fresh here, after ``generate()`` has already
    returned, closes that gap (#1598/#1584 review, item 7).
    """
    if not new_methods.strip():
        return InsertOutcome(False, "no methods generated")

    unsafe_categories = scan_for_unsafe_patterns(new_methods)
    if unsafe_categories:
        return InsertOutcome(False, f"refused — unsafe pattern(s): {unsafe_categories}")

    text = test_file.read_text(encoding="utf-8")

    dupes = detect_duplicate_methods(text, new_methods)
    if dupes:
        return InsertOutcome(False, f"duplicate method names: {dupes}")

    try:
        insert_before_class_close(test_file, new_methods, text)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")
