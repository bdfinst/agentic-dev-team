#!/usr/bin/env python3
"""Compute a changed-file list with git change-type (#1734).

`arch-review` (and every other `Context needs: project-structure` lens —
`doc-review`, `domain-review`) has no Bash grant, yet its dispatch payload
today is only "full files + directory tree". Nothing stops the agent from
reasoning that it should "see what changed" and attempting `git diff` itself
— a call it does not have, denied, and surfaced as a spurious error in its
report. The fix is not a new tool grant (that would be a first-of-its-kind
precedent for a review agent); it is completing the payload the orchestrator
already has the data for: a changed/added/removed file list alongside the
full files and tree.

This module is that data, computed once from `git diff --name-status` output
so `/code-review` never invents it twice: `SKILL.md` step 4 feeds it into the
`project-structure` context payload, and step 3 feeds its `added` list into
`select_lenses.py`'s `--added-from` flag for `component-architecture-review`'s
added-only `Scope:` gate (#1733) — one changed-file computation, two
consumers, not two ways to derive the same fact.

**A skipped line narrows, it does not widen.** A line this module cannot
parse (wrong field count, empty path) is skipped rather than guessed, never
fabricated — but for the added-only `Scope:` gate that consumes this
module's `added` list, dropping a genuinely-added path *removes* it from
`added` while it still reaches `select_lenses.py` independently via
`--files`, so the gate's `f in added_files` membership test then excludes
that lens rather than including it. A parse skip is a missed narrowing
*result* (the lens is lost, not kept) — do not read it as fail-open the way
this module's caller (`select_lenses.py`) is fail-open for a missing
`Scope:` declaration; the two failure directions are opposite.

**Only `status == "A"` counts as added — renames and copies do not.** A
rename (`R`) or copy (`C`) produces a path that did not previously exist,
but it carries no new content to assess (a rename) or duplicates content
already reviewed elsewhere (a copy, and only reachable at all when a caller
passes `-C`/`--find-copies`, which none of this module's callers do today).
This is a deliberate, narrow choice, not an oversight — widen it (e.g.
`status in ("A", "C")`) only with a test pinning the new behavior.

**Known limitation: a path git C-quotes is stored quoted, not unquoted.**
Git always quotes a control character (including an embedded newline) or a
literal backslash/double-quote in a path — regardless of `core.quotePath` —
by wrapping it in `"..."` with C-style escapes (verified empirically: a file
literally named with an embedded newline round-trips through `git diff
--name-status` as the single line `"a\nb.txt"`, quotes included). This
module does not strip that quoting, so such a path reaches `select_lenses.py`
still wrapped in `"..."`, and its `_matches()` suffix check (`.endswith(...)`)
then fails against every glob — the file is invisible to every non-`always`
lens. Narrow in practice (control characters in filenames are rare) and not
a regression this module introduces (the pre-existing `--name-only` listing
step 1 uses has the identical exposure); fixing it needs a C-quote-aware
unquote step here, not attempted in this pass.

Pure policy except for the one I/O boundary in `main()` (reading
`--name-status-from <file>`, guarded against a missing/unreadable path).
Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable


def parse_name_status(lines: Iterable[str]) -> list[dict]:
    """Parse `git diff --name-status` lines into `[{"path", "status"}, ...]`.

    Each line is `<status>\\t<path>`, or for a rename/copy
    `<status>\\t<old-path>\\t<new-path>` — the last field is always the
    current path, which is what every consumer here cares about. `status` is
    normalized to its leading letter (`R100` -> `R`) so callers compare
    against `A`/`M`/`D`/`R`/`C` without parsing similarity percentages.
    Unparseable lines are skipped, never raised on and never guessed.
    """
    files: list[dict] = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status_field = parts[0].strip()
        path = parts[-1].strip()
        if not status_field or not path:
            continue
        files.append({"path": path, "status": status_field[0]})
    return files


def evaluate(lines: Iterable[str]) -> dict:
    """Evaluate `git diff --name-status` lines into the full result dict."""
    files = parse_name_status(lines)
    return {
        "files": files,
        "added": [f["path"] for f in files if f["status"] == "A"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name-status", nargs="*", default=[],
        help="git diff --name-status lines, one per arg (space-separated)",
    )
    parser.add_argument(
        "--name-status-from", default=None,
        help="read newline-separated name-status lines from this file ('-' for stdin)",
    )
    args = parser.parse_args(argv)

    lines = list(args.name_status)
    if args.name_status_from:
        try:
            if args.name_status_from == "-":
                text = sys.stdin.read()
            else:
                with open(args.name_status_from) as handle:
                    text = handle.read()
        except (OSError, ValueError):
            # Missing/unreadable path, closed stdin, or undecodable bytes:
            # contribute no lines rather than crash the whole invocation —
            # consistent with every other unparseable-input case in this
            # module. `ValueError` also covers `UnicodeDecodeError` (a
            # subclass), reachable here because SKILL.md's caller mandates
            # `-c core.quotePath=false`, which makes git emit raw path bytes
            # instead of escaped octal for a non-ASCII path.
            text = ""
        lines.extend(line for line in text.splitlines() if line.strip())

    print(json.dumps(evaluate(lines), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = ("evaluate", "parse_name_status")
