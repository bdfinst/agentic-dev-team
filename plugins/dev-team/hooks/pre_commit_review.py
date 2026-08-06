#!/usr/bin/env python3
"""pre_commit_review — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-review.sh (#583 / #572 Cluster B), extended
under #709 (`--no-verify`/`-n` bypass-reason auditing), then hardened across
#1461/#1476/#1627/#1763/#1801 into a review-corroboration gate on
`git commit`.

**#1886 (design decision, resolved): this module is now a documented no-op.**
The review-corroboration gate moved from `git commit` to `gh pr create` — a
branch is now free to accumulate any number of local commits without paying
the review-panel cost at each one; the hard block fires once, against the
branch's FULL diff vs. its base, at PR-creation time. See
`hooks/pre_pr_review.py`, the successor hook, for the new mechanism, the
full "why a new module rather than repurposing this one in place" rationale,
and the deliberately-dropped-not-carried-forward list (multi-target `-C`
resolution, `-a`/pathspec-form-commit detection, cosmetic-delta
carry-forward — none of which apply to `gh pr create`'s command shape).

This file is kept in place — deliberately not deleted — rather than
removed, so the many docs/tests/skills that reference `pre_commit_review.py`
by name (describing this exact migration, or a bypass mechanism that is now
simply unnecessary rather than broken) keep resolving to a real file that
explains what happened, instead of a dangling reference. Every prior test
against this module's git-commit-gating behavior has had its INTENT ported
to `hooks/pre_pr_review.py`'s own test suite (#1886 acceptance criterion:
"existing pre_commit_review.py test suite's intent is preserved") — this
module's own remaining tests (`tests/hooks/test_pre_commit_review.py`) now
only pin the no-op contract below.

`git commit --no-verify`/bare `-n`, and the `GATE_BYPASS_REASON` env var,
are still accepted harmlessly by git itself and by any skill prose that
still mentions them (e.g. `/fix`'s per-cycle commit step) — they are simply
no longer meaningful to THIS hook, since there is no gate left to bypass.
Nothing needs to change in a caller that still sets them; they are now inert
input, not a contract this module still enforces.

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call — the ONLY exit code this module now
            produces, for every input, including malformed/absent stdin.

Stdlib-only.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Always allow. Reading stdin at all is unnecessary now that this hook
    makes the same decision regardless of payload content — but the
    contract (read stdin, then decide) is kept structurally identical to
    every other PreToolUse hook in this plugin, so a future reviewer sees
    the same shape they'd expect, not a surprising short-circuit before the
    stdin read."""
    sys.stdin.read()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a commit
        sys.exit(0)
