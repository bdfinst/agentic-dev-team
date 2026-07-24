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
reused here — not re-derived):

| Language | Framework                          | Pending marker              |
|----------|-------------------------------------|------------------------------|
| JS/TS    | Cucumber.js                         | `this.pending()`             |
| Java     | Cucumber-JVM                        | `PendingException`           |
| C#       | Reqnroll (xUnit/NUnit/MSTest)       | `StepIsPending()`             |
| Go       | Godog                                | `godog.ErrPending`           |

The language for a given step-definition file is resolved from its
extension — `.js`/`.ts`/`.mjs`/`.cjs` → JS/TS, `.java` → Java, `.cs` → C#,
`.go` → Go. Files with an unrecognized extension are skipped (not every file
under a step-definitions directory is necessarily a step-definition file).

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

# Extension -> (language label, pending marker substring).
_MARKERS_BY_EXT = {
    ".js": ("JS/TS", "this.pending()"),
    ".ts": ("JS/TS", "this.pending()"),
    ".mjs": ("JS/TS", "this.pending()"),
    ".cjs": ("JS/TS", "this.pending()"),
    ".java": ("Java", "PendingException"),
    ".cs": ("C#", "StepIsPending()"),
    ".go": ("Go", "godog.ErrPending"),
}


def find_step_definition_files(directories: list[Path]) -> list[Path]:
    """Return every file under `directories` whose extension is a known
    step-definition language, sorted for deterministic output."""
    found: list[Path] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in _MARKERS_BY_EXT:
                found.append(path)
    return sorted(set(found))


def find_pending_stubs(files: list[Path]) -> list[dict]:
    """Return one entry per pending-marker occurrence: {file, line, language, text}."""
    pending: list[dict] = []
    for path in files:
        language, marker = _MARKERS_BY_EXT[path.suffix]
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if marker in line:
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
    pending = find_pending_stubs(files)

    if args.json:
        print(json.dumps({"scanned": [str(f) for f in files], "pending": pending}, indent=2))
        return 1 if pending else 0

    if pending:
        print(f"FAIL: {len(pending)} pending step definition(s) — bdd-runner mode is not done:")
        for entry in pending:
            print(f"  - {entry['file']}:{entry['line']} ({entry['language']}) — {entry['text']}")
        return 1

    print(f"OK: {len(files)} step-definition file(s) scanned, no pending stubs remain.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
