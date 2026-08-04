"""pre_commit_detect — shared `git commit` detection for PreToolUse:Bash hooks.

Python port of hooks/lib/pre-commit-detect.sh (#576 / #572 Cluster B).
Extended under #709 to recognize bare `-n` as a bypass flag identically to
`--no-verify` (parity fix — `hooks/telemetry.py`'s bypass detection already
matched bare `-n`; this detector did not).

Imported by the Python siblings of the two callers:
  - hooks/pre_commit_review.py
  - hooks/pre_commit_knowledge_index.py

Exposes:

  is_git_commit_command(cmd: str) -> bool
    True when `cmd` is a `git commit` invocation, regardless of any
    bypass flag. Callers that need to distinguish "gate-worthy commit"
    from "bypassed commit" should also consult `has_bypass_flag`.

  has_bypass_flag(cmd: str) -> bool
    True when `cmd` carries `--no-verify` or a bare `-n` argument — git's
    two spellings of "skip hooks". Substring/word-bounded match; does not
    require `cmd` to be a `git commit` invocation.

  bypass_flag_name(cmd: str) -> Optional[str]
    "--no-verify" or "-n" (whichever matched; `--no-verify` preferred when
    both are present), or None when `cmd` carries no bypass flag.

  is_git_commit_invocation(cmd: str) -> bool
    True when `cmd` is a `git commit` we should gate on (no bypass flag).
    Kept for backward compatibility with existing callers/tests.

Stdlib-only. See docs/python-hook-contract.md.
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

# git's short-form bypass flag. Word-bounded (whitespace or string edges) so
# it doesn't false-positive inside `-nx` or `--number`. Mirrors
# `hooks/telemetry.py`'s `_NO_VERIFY_RE` pattern.
_BARE_N_RE = re.compile(r"(?:^|\s)-n(?:\s|$)")


def is_git_commit_command(cmd: str) -> bool:
    """Return True iff `cmd` is a `git commit` invocation (bypass or not)."""
    if not cmd:
        return False
    return bool(_GIT_COMMIT_RE.search(cmd))


def has_bypass_flag(cmd: str) -> bool:
    """Return True iff `cmd` carries `--no-verify` or a bare `-n` flag."""
    return bypass_flag_name(cmd) is not None


def bypass_flag_name(cmd: str) -> str | None:
    """Return which bypass flag matched (`--no-verify` preferred), or None."""
    if not cmd:
        return None
    if _NO_VERIFY_RE.search(cmd):
        return "--no-verify"
    if _BARE_N_RE.search(cmd):
        return "-n"
    return None


def is_git_commit_invocation(cmd: str) -> bool:
    """Return True iff `cmd` is a gate-worthy `git commit` invocation."""
    if not is_git_commit_command(cmd):
        return False
    return not has_bypass_flag(cmd)


__all__ = (
    "bypass_flag_name",
    "has_bypass_flag",
    "is_git_commit_command",
    "is_git_commit_invocation",
)
