#!/usr/bin/env python3
"""gherkin_stub_gate.py — fail closed while bdd-runner step definitions are
still pending (issue #1391).

`bdd-runner` mode wires a real native Gherkin parser (cucumber-js, Reqnroll,
cucumber-jvm, godog) and `gherkin-derive/SKILL.md` Step 4 generates **pending**
step-definition stubs so the suite compiles and fails intentionally (red
before green) — that scaffolding step is correct on its own. Choosing
`bdd-runner` mode is a decision to end up with fully executing, Gherkin-bound
tests, not a decision to scaffold placeholders that may or may not get
finished. This script is the completion gate: it greps the step-definition
files for the per-language pending marker and fails, listing every remaining
file:line, when any stub was never filled in.

Per-language pending markers (`gherkin-derive/SKILL.md` Step 4's table,
reused here — not re-derived). The extension -> (language label, markers)
table itself lives in `lib/_bdd_markers.py` (issue #1421 bug 5) — shared with
`lib/stub_extractors/__init__.py`, which needs the same mapping and used to
reach up into this module's `_MARKERS_BY_EXT` via a `sys.path` layer
inversion to get it. C# carries two markers: `PendingStepException`
is Reqnroll's current auto-suggested stub, and `StepIsPending()` is its
deprecated-since-3.3.4 predecessor — still recognized so an older or
not-yet-regenerated stub isn't a false negative
(`knowledge/test-stack-profiles/bdd-frameworks.md`):

| Language | Framework                          | Pending marker(s)                          |
|----------|-------------------------------------|----------------------------------------------|
| JS/TS    | Cucumber.js                         | `this.pending()`                             |
| Java     | Cucumber-JVM                        | `PendingException`                           |
| C#       | Reqnroll (xUnit/NUnit/MSTest)       | `PendingStepException`, `StepIsPending()`    |
| Go       | Godog                                | `godog.ErrPending`                           |

The language for a given step-definition file is resolved from its
extension, matched **case-insensitively** — `.js`/`.ts`/`.mjs`/`.cjs` →
JS/TS, `.java` → Java, `.cs` → C#, `.go` → Go. Files with an unrecognized
extension are skipped (not every file under a step-definitions directory is
necessarily a step-definition file). Vendored/generated trees
(`.git`, `node_modules`, `vendor`, `dist`, `build`, and virtualenv
directories) are pruned during the scan — the same exclusion set
`detect_bdd_convention.py` uses — so a stray dependency tree under a scanned
directory is never walked or grepped — via the shared `_vendored_tree.py`
helper (issue #1420), also used by `detect_bdd_convention.py` and
`gherkin_failure_path_gate.py`.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_stub_gate.py --dir <step-definitions-dir> [--dir <dir> ...]
    python3 gherkin_stub_gate.py --dir features/test-improve/my-slug --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

from _bdd_markers import MARKERS_BY_EXT as _MARKERS_BY_EXT
from _gherkin_text import safe_for_terminal as _safe_for_terminal
from _vendored_tree import find_files as _find_files


def find_step_definition_files(directories: list[Path]) -> list[Path]:
    """Return every file under `directories` whose extension is a known
    step-definition language (matched case-insensitively), pruning vendored
    trees, sorted for deterministic output."""
    return _find_files(directories, lambda path: path.suffix.lower() in _MARKERS_BY_EXT)


def _matching_marker(line: str, markers: tuple) -> str | None:
    """Return the first marker in `markers` that occurs in `line`, or
    `None` — the innermost scan of `find_pending_stubs`, extracted so that
    function stays at 2 levels of nesting instead of 4."""
    return next((marker for marker in markers if marker in line), None)


def find_pending_stubs(files: list[Path]) -> list[dict]:
    """Return one entry per pending-marker occurrence: {file, line, language, text}."""
    pending: list[dict] = []
    for path in files:
        language, markers = _MARKERS_BY_EXT[path.suffix.lower()]
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            marker = _matching_marker(line, markers)
            if marker is not None:
                pending.append(
                    {
                        "file": str(path),
                        "line": line_no,
                        "language": language,
                        "marker": marker,
                        "text": line.strip(),
                    }
                )
    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gherkin_stub_gate.py",
        description=(
            "Fail closed when any bdd-runner step-definition file still "
            "carries a pending-stub marker."
        ),
    )
    parser.add_argument(
        "--dir",
        dest="dirs",
        action="append",
        type=Path,
        required=True,
        help="Step-definitions directory to scan (repeatable).",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    files = find_step_definition_files(args.dirs)

    if not files:
        # Mirrors gherkin_failure_path_gate.py's identical fix: a --dir that
        # doesn't exist (or resolves to zero step-definition files) used to
        # silently report "OK: 0 ... scanned, no pending stubs remain" — an
        # affirmative all-clear for zero evidence. --dir is composed by
        # gherkin-derive from a probe of the target repo, not always typed
        # by a human, so a gate that scanned nothing must say so distinctly.
        dirs_display = ", ".join(str(d) for d in args.dirs)
        message = f"no step-definition files found under {dirs_display} — gate did not run"
        if args.json:
            print(json.dumps({"scanned": [], "pending": [], "warning": message}, indent=2))
        else:
            # --dir is composed by gherkin-derive from a probe of the target
            # repo, not always typed by a human — the same untrusted-path
            # class as a scanned file's path, sanitized the same way.
            print(
                f"WARN: no step-definition files found under "
                f"{_safe_for_terminal(dirs_display)} — gate did not run"
            )
        return 2

    pending = find_pending_stubs(files)

    if args.json:
        print(json.dumps({"scanned": [str(f) for f in files], "pending": pending}, indent=2))
        return 1 if pending else 0

    if pending:
        print(f"FAIL: {len(pending)} pending step definition(s) — bdd-runner mode is not done:")
        for entry in pending:
            path = _safe_for_terminal(entry["file"])
            text = _safe_for_terminal(entry["text"])
            print(f"  - {path}:{entry['line']} ({entry['language']}) — {text}")
        return 1

    print(f"OK: {len(files)} step-definition file(s) scanned, no pending stubs remain.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
