#!/usr/bin/env python3
"""Select which /setup Step 6 mutation-tooling sections to run (#1152).

`/setup` Step 6 installs per-language mutation tooling (Stryker for JS/TS,
pitest for Java/Kotlin, Stryker.NET for C#/.NET). Which sections run must be
strictly relative to the repo's detected stack — a JS-only or Python-only
repo must never probe for `dotnet`, `mvn`, or `node` outside its own stack.

This helper makes that decision deterministically instead of leaving it to
prose the agent can skip. It reads `.claude/project-stack.json`'s `stacks`
array once and maps stack tokens to sections:

    typescript / node   -> js       (Stryker)
    java / kotlin        -> java     (pitest)
    csharp / dotnet      -> csharp   (Stryker.NET)
    python                -> python  (mutmut)

Output is a single JSON object on stdout:

    {
      "sections": ["js"],        # sections to run, in canonical order
      "stacks": ["typescript"],  # the stacks array that was read
      "ambiguous": false,        # true ONLY when the stack signal is empty/missing
      "note": null               # one-line note when a stack matched no section
    }

Three distinct outcomes:

- Definite stack that maps to sections -> run ONLY those sections
  (`ambiguous` false, `note` null).
- Definite stack that maps to NO section (e.g. Ruby, Elixir — no mutation
  tool wired in for that stack) -> `sections` empty, `ambiguous` false,
  `note` set to `no mutation tooling for detected stack (<stacks>)`. Install
  nothing; probe nothing.
- Empty / missing / stacks-less signal -> `ambiguous` true. This is the ONLY
  outcome that authorizes the interactive "which languages?" fallback.

Usage:
    mutation_stack_sections.py [PROJECT_DIR]
    mutation_stack_sections.py --stacks typescript,node   # for testing

PROJECT_DIR defaults to the current directory; the stack file is read from
`<PROJECT_DIR>/.claude/project-stack.json`.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Canonical section order — polyglot repos run matching sections in this order.
SECTION_ORDER = ["js", "java", "csharp", "python"]

# Stack token (lowercased) -> section key.
STACK_TO_SECTION: dict[str, str] = {
    "typescript": "js",
    "node": "js",
    "javascript": "js",
    "java": "java",
    "kotlin": "java",
    "csharp": "csharp",
    "dotnet": "csharp",
    "python": "python",
}


def select_sections(stacks: list[str] | None) -> dict[str, object]:
    """Map a `stacks` array to the sections /setup Step 6 should run.

    Returns a dict with `sections`, `stacks`, `ambiguous`, and `note`.

    `stacks` None or empty -> ambiguous (the interactive fallback is allowed).
    A non-empty `stacks` that maps to no section is NOT ambiguous — it is a
    definite "no mutation tooling for this stack" outcome.
    """
    normalized = [str(s).strip().lower() for s in (stacks or []) if str(s).strip()]

    if not normalized:
        return {
            "sections": [],
            "stacks": normalized,
            "ambiguous": True,
            "note": None,
        }

    matched = {STACK_TO_SECTION[s] for s in normalized if s in STACK_TO_SECTION}
    sections = [s for s in SECTION_ORDER if s in matched]

    note = None
    if not sections:
        note = f"no mutation tooling for detected stack ({', '.join(normalized)})"

    return {
        "sections": sections,
        "stacks": normalized,
        "ambiguous": False,
        "note": note,
    }


def read_stacks(project_dir: Path) -> list[str] | None:
    """Return the `stacks` array from `<project_dir>/.claude/project-stack.json`.

    Returns None when the file is missing, unreadable, not valid JSON, or has
    no `stacks` key — all of which collapse to the ambiguous outcome.
    """
    stack_file = project_dir / ".claude" / "project-stack.json"
    try:
        data = json.loads(stack_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    stacks = data.get("stacks")
    if not isinstance(stacks, list):
        return None
    return stacks


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory (default: current directory).",
    )
    parser.add_argument(
        "--stacks",
        default=None,
        help="Comma-separated stacks to use directly, bypassing the file (testing).",
    )
    args = parser.parse_args(argv[1:])

    if args.stacks is not None:
        stacks: list[str] | None = [s for s in args.stacks.split(",") if s.strip()]
    else:
        stacks = read_stacks(Path(args.project_dir))

    print(json.dumps(select_sections(stacks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
