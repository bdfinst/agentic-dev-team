"""review_gate_hash — single source of truth for the .review-passed gate hash.

Python port of hooks/lib/review-gate-hash.sh (#576 / #572 Cluster B, #193).

The review gate binds to the STAGED CONTENT (the cached patch), not just
the staged file PATHS. Hashing paths alone let a reviewed file's content
change and still commit unreviewed. Hashing `git diff --cached` captures
both which files are staged AND their staged content — so any edit after
review invalidates the gate and forces a re-review.

Both the writer (`/code-review` step 9) and the reader (pre_commit_review)
MUST compute the hash identically. This module IS that shared computation.

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.

Byte-parity note: `git diff --cached --no-color` is invariant across bash
and Python callers because git itself owns the format. sha256 hex-encoded
matches the `shasum -a 256 | cut -d' ' -f1` pipeline the .sh uses.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional


def review_gate_hash(cwd: Optional[Path] = None) -> str:
    """Return the sha256 hex digest of `git diff --cached --no-color`.

    Byte-parity with the .sh sibling:
      - `git diff --cached --no-color 2>/dev/null` — same command
      - sha256 hex-encoded — same digest
      - empty output on git failure — same failure mode
    """
    try:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--no-color"],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # git not installed; the .sh would have `command not found` on stderr
        # and an empty stdout piped through shasum → sha256 of empty input.
        # We return the same empty-input digest to keep byte-parity.
        return hashlib.sha256(b"").hexdigest()

    if completed.returncode != 0:
        # `git diff --cached` outside a repo prints to stderr and exits non-0
        # with empty stdout; the .sh pipes that empty stdout into shasum,
        # yielding the sha256 of empty input. Mirror that.
        return hashlib.sha256(b"").hexdigest()

    return hashlib.sha256(completed.stdout).hexdigest()


def _main() -> int:
    """When the .sh is executed directly it prints the hash. Same for us."""
    print(review_gate_hash())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ("review_gate_hash",)
