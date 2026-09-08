#!/usr/bin/env python3
"""Language-neutral internal-double detector with waiver support (#2127).

Implements the unconditional rule in `knowledge/internal-collaborator-doubling.md`
(#2124): a collaborator declared in the project's own first-party source
stays real; a double is admissible only when the collaborator matches one
of three named blockers (B1 out-of-process handle, B2 ambient state, B3
prohibitive real cost), marked with an inline `double-waiver: B<n> — <reason>`
comment at the double site.

**No test-type gate.** The rule is unconditional, so this detector reads no
test-type declaration (solitary/sociable/unit/component/anything else) —
that is what closes the undeclared-file and relabel bypasses the epic's
architecture notes describe. A file is scanned the same way regardless of
what it calls itself.

**Language-neutral by construction.** One first-party declaration index plus
per-stack *data* tables (`_EXTRACTION_TABLES`, `_AMBIENT_API_MARKERS`) feed a
single shared pipeline (`extract_by_table`, `analyze`). There is no
per-language branching logic — a new stack is a new data-table row, not a
new code path. If this module exceeds ~500 lines, split the extraction
tables into a submodule rather than growing this file indefinitely (mirrors
`repo_invariants.py`'s own "start narrow, expand opportunistically"
convention) — not yet warranted at this size.

**What this detector verifies, and what it does not:**

- Resolution is **name-based, not fully-qualified-path-based**. Building a
  real cross-file import graph per language is out of scope for a
  stdlib-only script with no per-language parser. A name match against the
  first-party declaration index is treated as resolved. Two same-named
  types in different first-party modules are indistinguishable; a name
  collision with an unrelated third-party type of the same name could
  false-positive. Precision-first per the epic means under-report, not zero
  false positives.
- **Waiver syntax, not waiver truth**, for B1 and B3. A waiver naming B1 or
  B3 is `informational` once its code is syntactically valid — this
  detector cannot decide whether the claimed out-of-process handle or
  prohibitive cost is real (the epic's own architecture notes: B1 is "not
  decidable", B3 "not statically detectable at all"). `test-smell-review`
  owns that judgment.
- **B2 gets one mechanical evidence check**, not full verification: the
  epic states B2 (unlike B1/B3) is "detectable against a per-stack table of
  ambient APIs." A B2 waiver is downgraded from `informational` to `high`
  when the doubled collaborator's own declaring file shows no reference to
  any per-stack ambient-API marker (clock, RNG/GUID, env, hostname, cwd,
  locale) — a presence-of-reference check, not a behavioral proof.
  `test-smell-review` still owns the final call even when this check
  passes.
- Gate-wiring into a blocking hook or CI check is a separate issue (#2128).
  This script is a standalone CLI, proven via direct invocation and its own
  test suite.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

# --- First-party type resolution --------------------------------------------

#: Directory names excluded from vendored/generated/build-output code for
#: *both* first-party indexing and double scanning — nothing useful lives
#: there for either purpose.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "vendor",
        "vendored",
        ".git",
    }
)

#: Test-directory names excluded from first-party resolution ONLY — a type
#: declared under a test tree isn't a first-party collaborator (#2124's
#: rule is about the project's own *non-test* source). These directories
#: are NOT excluded from double-scanning: that's exactly where doubles live.
_TEST_DIR_NAMES = frozenset({"test", "tests"})

#: (stack, compiled_regex, target_group) rows for declaring a first-party
#: type. One row per declaration *form*, not one combined regex per stack
#: with post-hoc form selection (design-review fix) — a new form is a new
#: row, never a new branch.
_TYPE_DECLARATION_TABLE: tuple[tuple[str, re.Pattern, int], ...] = (
    ("python", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"), 1),
    ("csharp", re.compile(r"^\s*(?:public|internal|private)?\s*(?:class|interface|record)\s+([A-Za-z_][A-Za-z0-9_]*)"), 1),
    ("java", re.compile(r"^\s*(?:public|private|protected)?\s*(?:class|interface|record)\s+([A-Za-z_][A-Za-z0-9_]*)"), 1),
    ("js_ts_class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"), 1),
    ("js_ts_interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"), 1),
    ("js_ts_type_alias", re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)\s*="), 1),
)


def _is_vendored_or_build(path: Path) -> bool:
    return any(part.lower() in _EXCLUDED_DIR_NAMES for part in path.parts)


def _is_test_tree(path: Path) -> bool:
    return any(part.lower() in _TEST_DIR_NAMES for part in path.parts)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


#: Source file extensions this detector reads at all — first-party
#: resolution and every extraction vector below are scoped to these.
_SOURCE_EXTENSIONS = frozenset({".py", ".cs", ".java", ".ts", ".tsx", ".js", ".jsx"})

#: Which file extensions each stack's patterns are allowed to run against.
#: Without this, a stack's regex can spuriously match inside another
#: stack's file (e.g. a C# "class X : Base" pattern's trailing `\s*` can
#: cross a newline and match text in an unrelated Python file) — extension
#: gating is what actually keeps the per-stack data tables from bleeding
#: into each other, not just their labels.
_STACK_EXTENSIONS: dict[str, frozenset[str]] = {
    "python": frozenset({".py"}),
    "csharp": frozenset({".cs"}),
    "java": frozenset({".java"}),
    "js_ts": frozenset({".ts", ".tsx", ".js", ".jsx"}),
    "js_ts_class": frozenset({".ts", ".tsx", ".js", ".jsx"}),
    "js_ts_interface": frozenset({".ts", ".tsx", ".js", ".jsx"}),
    "js_ts_type_alias": frozenset({".ts", ".tsx", ".js", ".jsx"}),
}


def resolve_first_party_types(root: Path) -> dict[str, Path]:
    """Index every type name declared in non-test, non-vendored,
    non-generated source under `root`. Returns `{type_name: declaring_path}`
    — first declaration wins on a name collision (a recall bound stated in
    the module docstring, not silently hidden).
    """
    index: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_EXTENSIONS:
            continue
        rel = path.relative_to(root)
        if _is_vendored_or_build(rel) or _is_test_tree(rel):
            continue
        text = _read_text(path)
        if not text:
            continue
        for stack, pattern, group in _TYPE_DECLARATION_TABLE:
            if path.suffix not in _STACK_EXTENSIONS.get(stack, _SOURCE_EXTENSIONS):
                continue
            for line in text.splitlines():
                m = pattern.match(line)
                if m:
                    name = m.group(group)
                    index.setdefault(name, path)
    return index


# --- Extraction tables (doubling constructs, hand-rolled, DI-override) -----

def _identity(name: str) -> str:
    return name


def _last_path_segment(module_path: str) -> str:
    """`./services/SmtpGateway` -> `SmtpGateway` — `vi.mock`/`jest.mock`
    capture a module *path*, not a type name, so the target must be
    normalized to a plausible type-name form before it can be looked up in
    the name-keyed first-party index (correctness-review fix: these rows
    previously could never resolve to anything but `advisory`)."""
    stem = module_path.rsplit("/", 1)[-1]
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        stem = stem.removesuffix(ext)
    return stem


def _last_dotted_segment(dotted: str) -> str:
    """`billing.SmtpGateway` -> `SmtpGateway` — `vi.spyOn` can capture a
    dotted expression; only the final segment is a plausible type name."""
    return dotted.rsplit(".", 1)[-1]


#: One shared schema for every extraction vector: a tuple of
#: `(stack, compiled_regex, target_group, normalize)` rows, where
#: `normalize` maps the raw captured string to a plausible type name before
#: first-party lookup (identity for rows that already capture a bare type
#: name). `extract_by_table` is the single iteration helper every vector
#: uses — no vector gets its own bespoke loop (design-review fix).
_EXTRACTION_TABLES: dict[str, tuple[tuple[str, re.Pattern, int, Callable[[str], str]], ...]] = {
    "mock_construct": (
        ("csharp", re.compile(r"\bMock<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("csharp", re.compile(r"\bMock\.Of<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("csharp", re.compile(r"\bSubstitute\.For<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("csharp", re.compile(r"\bA\.Fake<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("java", re.compile(r"\bmock\(([A-Za-z_][A-Za-z0-9_]*)\.class\)"), 1, _identity),
        ("java", re.compile(r"@Mock(?:Bean)?\s*\n?\s*(?:private|public)?\s*([A-Za-z_][A-Za-z0-9_]*)\s+\w+;"), 1, _identity),
        ("js_ts", re.compile(r"\bvi\.mock\(\s*['\"]([^'\"]+)['\"]"), 1, _last_path_segment),
        ("js_ts", re.compile(r"\bjest\.mock\(\s*['\"]([^'\"]+)['\"]"), 1, _last_path_segment),
        ("js_ts", re.compile(r"\bvi\.spyOn\(\s*([A-Za-z_][A-Za-z0-9_.]*)"), 1, _last_dotted_segment),
        ("python", re.compile(r"\bpatch\(\s*['\"][\w.]*\.([A-Za-z_][A-Za-z0-9_]*)['\"]"), 1, _identity),
        ("python", re.compile(r"\bMagicMock\(\s*spec\s*=\s*([A-Za-z_][A-Za-z0-9_]*)"), 1, _identity),
    ),
    "hand_rolled": (
        # re.MULTILINE is required (correctness-review fix): extract_by_table
        # runs finditer over the WHOLE file, not line-by-line, so a bare `^`
        # only anchors to offset 0 without it — silently matching nothing
        # in any file with content before the fake class.
        ("python", re.compile(r"^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\(([A-Za-z_][A-Za-z0-9_]*)\)", re.MULTILINE), 1, _identity),
        ("java", re.compile(r"^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\s+implements\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE), 1, _identity),
        ("js_ts", re.compile(r"^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\s+implements\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE), 1, _identity),
        ("csharp", re.compile(r"^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\s*:\s*([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE), 1, _identity),
    ),
    "di_override": (
        ("csharp", re.compile(r"\bRemoveAll<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("csharp", re.compile(r"\bAddSingleton<([A-Za-z_][A-Za-z0-9_]*)>"), 1, _identity),
        ("java", re.compile(r"@Bean\s*\n?\s*(?:public|private)?\s*([A-Za-z_][A-Za-z0-9_]*)\s+\w+\("), 1, _identity),
        ("python", re.compile(r"\bdependency_overrides\[([A-Za-z_][A-Za-z0-9_]*)\]"), 1, _identity),
        ("js_ts", re.compile(r"\boverrideProvider\(([A-Za-z_][A-Za-z0-9_]*)\)"), 1, _identity),
    ),
}


def extract_by_table(
    text: str,
    table: tuple[tuple[str, re.Pattern, int, Callable[[str], str]], ...],
    file_ext: str | None = None,
) -> list[tuple[int, str, str]]:
    """Run every `(stack, regex, group, normalize)` row in `table` against
    `text`, returning `(line_no, stack, normalized_target_name)` for each
    match. Matches over the full text (not line-by-line) so a row's own
    regex controls whether it spans one line or several (e.g. a `@Bean`
    annotation on the line before the method it decorates) — the line
    number is derived from the match's start offset. When `file_ext` is
    given, a row only runs if its stack's extension set includes it — this
    is what stops one stack's pattern from matching inside another stack's
    file (see `_STACK_EXTENSIONS`'s docstring). Shared by every extraction
    vector — mock constructs, hand-rolled subclasses, and DI-override
    bindings alike."""
    out: list[tuple[int, str, str]] = []
    for stack, pattern, group, normalize in table:
        if file_ext is not None and file_ext not in _STACK_EXTENSIONS.get(
            stack, _SOURCE_EXTENSIONS
        ):
            continue
        for m in pattern.finditer(text):
            lineno = text.count("\n", 0, m.start()) + 1
            out.append((lineno, stack, normalize(m.group(group))))
    return out


def find_doubles(text: str, file_ext: str | None = None) -> list[tuple[int, str, str]]:
    return extract_by_table(text, _EXTRACTION_TABLES["mock_construct"], file_ext)


# --- Waiver parsing ----------------------------------------------------------

_WAIVER_RE = re.compile(r"double-waiver:\s*([A-Za-z0-9]+)\s*[—-]\s*(.+)")
_VALID_BLOCKERS = frozenset({"B1", "B2", "B3"})


def find_waiver(lines: list[str], double_line_no: int) -> tuple[str, str] | None:
    """Look at the double's own line and the line immediately before it for
    a `double-waiver: B<n> — <reason>` comment. Returns `(code, reason)` or
    `None`."""
    for idx in (double_line_no - 1, double_line_no - 2):
        if 0 <= idx < len(lines):
            m = _WAIVER_RE.search(lines[idx])
            if m:
                return m.group(1), m.group(2).strip()
    return None


def valid_blocker(code: str) -> bool:
    return code in _VALID_BLOCKERS


# --- Ambient-API evidence (B2 only) ------------------------------------------

#: Per-stack markers whose presence in a collaborator's own declaring file
#: is evidence it plausibly reads ambient state (clock, RNG/GUID, env,
#: hostname, cwd, locale). Presence-of-reference only — not a behavioral
#: proof. B1 and B3 have no equivalent table: the epic states both are
#: undecidable/not-statically-detectable, so this asymmetry is deliberate.
_AMBIENT_API_MARKERS: dict[str, tuple[str, ...]] = {
    "python": ("time.", "datetime.", "random.", "uuid.", "os.environ", "socket.gethostname", "os.getcwd", "locale."),
    "csharp": ("DateTime.Now", "Guid.NewGuid", "Environment."),
    "java": ("System.currentTimeMillis", "UUID.randomUUID", "System.getenv"),
    "js_ts": ("Date.now", "Math.random", "process.env"),
}


def references_ambient_api(collaborator_source: str, stack: str) -> bool:
    markers = _AMBIENT_API_MARKERS.get(stack, ())
    return any(marker in collaborator_source for marker in markers)


# --- Verdict computation ------------------------------------------------------

#: Findings dict shape: {line, stack, target, vector, verdict, waiver, message}
Finding = dict


def _verdict_for(
    waiver: tuple[str, str] | None,
    stack: str,
    collaborator_path: Path | None,
) -> str:
    if waiver is None:
        return "high"
    code, _reason = waiver
    if not valid_blocker(code):
        return "high"
    if code == "B2":
        collaborator_source = _read_text(collaborator_path) if collaborator_path else ""
        if not references_ambient_api(collaborator_source, stack):
            return "high"
    return "informational"


def _remediation_hint(target: str) -> str:
    return (
        f"add a `double-waiver: B<n> — <reason>` comment at the double site "
        f"naming why {target} can't stay real, or use the real collaborator. "
        "See knowledge/internal-collaborator-doubling.md."
    )


def analyze(root: Path) -> list[Finding]:
    """Scan every test-tree source file under `root` for doubles of
    first-party collaborators across all three vectors (mock constructs,
    hand-rolled subclasses, DI-overrides), and compute each one's verdict.

    Scoped to test-tree files (correctness-review fix): the epic's own
    language for both hand-rolled doubles ("a test-tree class implementing
    a first-party abstraction") and DI-overrides ("a type declared under
    the test tree") makes this explicit — a "double" is a test-context
    concept, so ordinary production subclassing of a first-party class is
    not in scope for any of the three vectors, not just these two.
    """
    first_party = resolve_first_party_types(root)
    findings: list[Finding] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_EXTENSIONS:
            continue
        rel_for_scope = path.relative_to(root)
        if _is_vendored_or_build(rel_for_scope) or not _is_test_tree(rel_for_scope):
            continue
        text = _read_text(path)
        if not text:
            continue
        lines = text.splitlines()

        for vector in ("mock_construct", "hand_rolled", "di_override"):
            matches = extract_by_table(text, _EXTRACTION_TABLES[vector], path.suffix)
            for lineno, stack, target in matches:
                collaborator_path = first_party.get(target)
                if collaborator_path is None:
                    verdict = "advisory"
                else:
                    waiver = find_waiver(lines, lineno)
                    verdict = _verdict_for(waiver, stack, collaborator_path)

                rel = str(path)
                findings.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "stack": stack,
                        "vector": vector,
                        "target": target,
                        "verdict": verdict,
                        "message": (
                            f"{rel}:{lineno}: {verdict} — {vector} of {target!r}"
                            + (
                                f". {_remediation_hint(target)}"
                                if verdict == "high"
                                else ""
                            )
                        ),
                    }
                )
    return findings


# --- CLI ----------------------------------------------------------------------

_RECALL_BOUNDS_STATEMENT = (
    "Recall bounds: type resolution is name-based, not fully-qualified — a "
    "same-named third-party type can false-positive, and a re-exported/"
    "aliased first-party type can be missed. Waiver checks verify syntax "
    "for B1/B3 (undecidable per the epic) and one mechanical ambient-API "
    "evidence check for B2 only — never full waiver truth. "
    "test-smell-review owns the final judgment call in every case."
)


def _summarize(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    if not counts:
        return "0 findings"
    return ", ".join(f"{n} {v}" for v, n in sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Directory to scan")
    parser.add_argument(
        "--strict", action="store_true", help="Exit nonzero if any 'high' finding exists"
    )
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"error: path not found: {root}", file=sys.stderr)
        return 2

    findings = analyze(root)

    if args.json:
        print(json.dumps({"findings": findings}, sort_keys=True))
    else:
        print(_summarize(findings))
        for f in findings:
            print(f["message"])
        print(_RECALL_BOUNDS_STATEMENT)

    if args.strict and any(f["verdict"] == "high" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
