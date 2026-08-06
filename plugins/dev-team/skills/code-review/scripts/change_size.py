#!/usr/bin/env python3
"""Classify a changeset's size to gate the /code-review agent panel (#1339).

`/code-review` Step 3 dispatches the full ~17-agent `Scope: always` panel on
every review regardless of diff size — a 2-line registry-table-row removal
(issue #1331's fix: 2 files, ~1 added line) pays the same review cost as a
25-file structural migration (issue #1334's fix: 537 added lines). The
pre-PR hook (`hooks/pre_pr_review.py`, #1886) has no coupling to which or how
many agents ran — it only checks that `/code-review` produced a matching
`.pr-review-passed` hash — so the panel-size decision is entirely Step 3's to
make, and today it makes no such distinction.

This module is the deterministic gate, sibling to `change_shape.py` (#1254,
which gates by file *type*). This gate gates by file *size*: given the target
files' `git diff --numstat` lines, it decides whether the changeset qualifies
for a narrowed agent panel.

**Added lines only, not deleted.** Added lines are unverified, newly
introduced content a reviewer must actually check; deleted lines are
comparatively low-risk (a dangling reference from a large deletion breaks the
build/tests, not silently). This is what lets issue #1331's fix (97 deleted
lines, ~1 added) qualify while issue #1334's fix (537 added lines) does not —
weighting total added+deleted would keep #1331's fix on the slow path,
defeating this gate's own motivating example.

**Gate-machinery carve-out.** Any file under `hooks/` or `skills/code-review/`
— the enforcement mechanism and this gate's own review orchestration —
always disqualifies, at any size. A change to the gate's own logic is exactly
the case where a cheap, self-certifying review would be a problem, so it is
excluded from ever qualifying for the shortcut it defines.

**Fail-safe by construction**, mirroring `change_shape.py`'s own philosophy:
a `git diff --numstat` failure, a binary-file marker (`-\t-\tpath`), or any
line this module cannot parse disqualifies the gate for that run (full
panel) — never counts as "small enough" by omission.

**Applicability is Step 3's job, not this module's.** This gate only makes
sense when there is an actual diff to measure (auto-scoped uncommitted
changes, or `--since <ref>`) — `--path`, `--all`, and the full-repository
fallback review complete files, not a diff, so `SKILL.md` never invokes this
module for those scopes. That decision is documented in `SKILL.md` Step 3's
"Change-size gate" subsection, not enforced here.

Pure policy — no filesystem, no globals. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import NamedTuple

# Thresholds calibrated against two real commits cited in spec #1345:
# issue #1331's fix (2 files, ~1 added line — should qualify) and issue
# #1334's fix (25 files, 537 added lines — should not). Hardcoded, not a new
# review-config.json surface — smallest change that solves the stated
# problem; revisit if real usage shows these miscalibrated.
MAX_FILES = 3
MAX_ADDED_LINES = 20

# The agents that stay meaningful at any diff size and survive the fast path:
# a single line can introduce a vulnerability (security-review), a logic
# defect (correctness-review), a spec mismatch (spec-compliance-review), or
# doc drift (doc-review). Every other `Scope: always` agent is primarily a
# code-quality-at-scale concern a diff this small essentially cannot exhibit
# meaningfully.
#
# KEEP THIS IN SYNC with the identically-named list restated in English in
# `code-review/SKILL.md`'s "Change-size gate" subsection (Step 3) — same
# single-source-of-truth risk `change_shape.py`'s `LOW_YIELD_LENSES` already
# carries against its own `SKILL.md` restatement.
FAST_PATH_AGENTS = [
    "security-review",
    "correctness-review",
    "spec-compliance-review",
    "doc-review",
]

# Path segments marking the review/gate machinery itself. A change here is
# exactly the case where a cheap, self-certifying review is a safety problem,
# so it always disqualifies, regardless of size. Narrower than
# `change_shape.py`'s "functional Claude-config" carve-out (agents/,
# knowledge/, .claude/, templates/) — those stay eligible for the fast path
# when small enough, since issue #1331's own motivating example touches
# `knowledge/agent-registry.md` and an `agents/` file and is exactly the case
# this gate must unblock.
_GATE_MACHINERY_PREFIXES = ("hooks/", "skills/code-review/")


class NumstatResult(NamedTuple):
    file_count: int
    added_lines: int
    ok: bool
    files: tuple[str, ...]


def parse_numstat(lines: Iterable[str]) -> NumstatResult:
    """Parse `git diff --numstat` lines into a size signal.

    Each line is `<added>\\t<deleted>\\t<path>`. A binary file reports `-` for
    both counts; any line that isn't exactly that shape, or whose added/
    deleted fields aren't parseable as non-negative integers (or `-`), marks
    the whole result not-ok (fail-safe — a partial read is not "small").
    """
    files: list[str] = []
    added_total = 0
    ok = True
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            ok = False
            continue
        added_field, deleted_field, path = parts
        if not path.strip():
            ok = False
            continue
        if added_field == "-" and deleted_field == "-":
            # Binary file — numstat can't report line counts. Fail-safe: we
            # cannot prove this file is small, so disqualify the whole run.
            ok = False
            files.append(path)
            continue
        if not added_field.isdigit() or not deleted_field.isdigit():
            ok = False
            continue
        added_total += int(added_field)
        files.append(path)
    return NumstatResult(
        file_count=len(files), added_lines=added_total, ok=ok, files=tuple(files)
    )


def is_gate_machinery(path: str) -> bool:
    """True when `path` is under the review/gate enforcement machinery."""
    normalized = str(path).strip().replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in _GATE_MACHINERY_PREFIXES)


def qualifies_for_fast_path(result: NumstatResult) -> bool:
    """True when this changeset qualifies for the narrowed fast-path panel.

    Requires: numstat parsed cleanly, file count and added-line count both
    within threshold, and no file is gate machinery. Any single failing
    condition disqualifies (fail-safe by construction).
    """
    if not result.ok:
        return False
    if result.file_count == 0:
        return False
    if result.file_count > MAX_FILES:
        return False
    if result.added_lines > MAX_ADDED_LINES:
        return False
    return not any(is_gate_machinery(f) for f in result.files)


def evaluate(lines: Iterable[str]) -> dict:
    """Evaluate numstat lines and return the full decision as a dict."""
    result = parse_numstat(lines)
    qualifies = qualifies_for_fast_path(result)
    return {
        "filesChanged": result.file_count,
        "addedLines": result.added_lines,
        "qualifiesForFastPath": qualifies,
        "keepAgents": list(FAST_PATH_AGENTS) if qualifies else [],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--numstat", nargs="*", default=[],
        help="git diff --numstat lines, one per arg (space-separated)",
    )
    parser.add_argument(
        "--numstat-from", default=None,
        help="read newline-separated numstat lines from this file ('-' for stdin)",
    )
    args = parser.parse_args(argv)

    lines = list(args.numstat)
    if args.numstat_from:
        if args.numstat_from == "-":
            text = sys.stdin.read()
        else:
            with open(args.numstat_from) as handle:
                text = handle.read()
        lines.extend(line for line in text.splitlines() if line.strip())

    print(json.dumps(evaluate(lines), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = (
    "FAST_PATH_AGENTS",
    "MAX_ADDED_LINES",
    "MAX_FILES",
    "NumstatResult",
    "evaluate",
    "is_gate_machinery",
    "parse_numstat",
    "qualifies_for_fast_path",
)
