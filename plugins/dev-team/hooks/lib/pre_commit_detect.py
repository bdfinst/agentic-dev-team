"""pre_commit_detect — shared `git commit` detection for PreToolUse:Bash hooks.

Python port of hooks/lib/pre-commit-detect.sh (#576 / #572 Cluster B).

Imported by the Python siblings of the two callers:
  - hooks/pre_commit_review.py
  - hooks/pre_commit_knowledge_index.py

Exposes one function:

  is_git_commit_invocation(cmd: str) -> bool

  True when `cmd` is a `git commit` we should gate on, False otherwise.
  Treats `--no-verify` as the documented bypass — the standard git escape
  hatch keeps working.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import re


# Word-bounded `git commit` at the start of the (leading-whitespace-tolerant)
# command line. Mirrors the .sh's `^[[:space:]]*git[[:space:]]+commit\b` ERE.
_GIT_COMMIT_RE = re.compile(r"^\s*git\s+commit\b")

# The documented bypass. Substring match (no word boundary) — mirrors the
# .sh's `grep -qE -- '--no-verify'` byte-for-byte: `--no-verifying`, though
# not a real git flag, also short-circuits under the .sh, so the port does
# the same. Byte-parity is the migration contract.
_NO_VERIFY_RE = re.compile(r"--no-verify")


def is_git_commit_invocation(cmd: str) -> bool:
    """Return True iff `cmd` is a gate-worthy `git commit` invocation."""
    if not cmd:
        return False
    if not _GIT_COMMIT_RE.search(cmd):
        return False
    if _NO_VERIFY_RE.search(cmd):
        return False
    return True


__all__ = ("is_git_commit_invocation",)
