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

The `.sh` sibling this module ported was retired in #618 — there is no
second implementation left to stay byte-parity with. `review_gate_hash()`'s
own docstring documents the current git invocation, including the config
overrides pinned off by later #1461 security re-reviews.

Known limitation (issue #1461): this hash proves the STAGED CONTENT hasn't
changed since a `.review-passed` file was written — it does NOT prove an
independent review actually produced that file. `review_gate_hash()` is a
small, public, pure function; any agent (including the one whose own work is
being gated) can import it, or reimplement the equivalent
`git diff --cached --no-color | sha256sum` pipeline, and self-write a
matching `.review-passed` without any independent review ever running.
Closing that gap with cryptographic hardening (e.g. requiring the file to be
signed by a token only genuine Agent-tool dispatch can produce) is out of
scope for this module and for `pre_commit_review.py` — it needs
infrastructure changes to the Agent-tool dispatch mechanism itself. The
mitigation that does exist lives one layer up, in the calling skills:
`skills/code-review/SKILL.md`, `skills/plan/SKILL.md`, and
`skills/build/SKILL.md` each carry a hard "confirm Agent/Task tool
availability before dispatching any review agent, or STOP" instruction, so a
session without real dispatch capability refuses to self-certify a review
rather than writing this gate file on its own say-so. This hash mechanism's
real integrity therefore depends on the calling skill's own honesty about
whether it actually dispatched independent reviewers — not on anything this
function can verify by itself.

`hooks/lib/review_gate_corroboration.py` (#1461) closes part of this gap:
it cross-references `hooks/agent_dispatch_ledger.py`'s recorded dispatch
evidence so `pre_commit_review.py` can require genuine, recent, distinct
review-agent dispatches in addition to this hash match — not instead of it.
That module is kept deliberately separate from this one: this module stays
a small, pure hash function with no registry or metrics-stream knowledge;
the corroboration module owns that heavier responsibility on its own.

The `-c diff.relative=false` / `--ignore-submodules=none` safety flags below
are shared with `hooks/pre_commit_review.py`'s `_staged_names()` via
`hooks/lib/git_safe_diff.py` (#1477) rather than duplicated here — see that
module's docstring for the full rationale of each shared flag.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from git_safe_diff import run_safe_git_diff  # noqa: E402


def review_gate_hash(cwd: Path | None = None) -> str:
    """Return the sha256 hex digest of `git diff --cached`, rendered with
    git's own built-in diff engine — cwd-relative and submodule-ignoring
    config, plus any external diff/textconv driver, are all deliberately
    pinned off (#1461 third/fourth/fifth security re-review). This is NOT
    simply `git diff --cached --no-color` under a non-default config —
    that divergence from the literal command text is the point.

    `-c diff.relative=false` and `--ignore-submodules=none` are the shared
    flags from `git_safe_diff.run_safe_git_diff` (see that module's
    docstring for the full rationale of each). `--no-color --no-ext-diff
    --no-textconv` are passed as this function's own `extra_flags` (#1461
    FOURTH security re-review, error-severity): without them, a
    `diff.external` config or a `GIT_EXTERNAL_DIFF` env var replaces git's
    own diff rendering entirely — including the `diff --git`/`index`
    headers this hash is computed over. `git config diff.external
    /usr/bin/true` would otherwise collapse this function's output to
    `sha256(b"")` for EVERY changeset, turning `subject_hash` into a
    CONSTANT: one honest `/code-review`'s genuine, unforged ledger
    dispatches would then corroborate every subsequent arbitrary changeset
    within the recency window, defeating the whole subject-binding fix
    without forging anything.

    sha256 hex-encoded; empty-input digest (`sha256(b"")`) on git failure.
    """
    try:
        completed = run_safe_git_diff(
            ["--no-color", "--no-ext-diff", "--no-textconv"],
            cwd=cwd,
            text=False,
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


def working_tree_gate_hash(cwd: Path | None = None) -> str:
    """Return the sha256 hex digest of `git diff HEAD` — the EFFECTIVE
    content (staged + unstaged, relative to HEAD) a `git commit -a`/`--all`
    or pathspec-form commit would actually commit (#1476).

    `review_gate_hash()` above hashes `git diff --cached`, which is empty
    by definition for these commit forms (nothing was ever `git add`-ed) —
    using it here would let such a commit sail through on an empty-hash
    match. This sibling function is otherwise identical: same shared safety
    flags via `git_safe_diff.run_safe_git_diff` (just `target="HEAD"`
    instead of the default `"--cached"`), same `--no-color --no-ext-diff
    --no-textconv` extra flags, same empty-input digest on git failure.
    Kept in lockstep with `review_gate_hash()` deliberately — a future
    safety-flag fix applied to one and forgotten on the other would reopen
    exactly the subject-binding bypass both functions exist to prevent.
    """
    try:
        completed = run_safe_git_diff(
            ["--no-color", "--no-ext-diff", "--no-textconv"],
            cwd=cwd,
            text=False,
            target="HEAD",
        )
    except (FileNotFoundError, OSError):
        return hashlib.sha256(b"").hexdigest()

    if completed.returncode != 0:
        # Includes the unborn-HEAD case (a repo with no commits yet) —
        # `git diff HEAD` fails there just like `git diff --cached` fails
        # outside a repo. Fail-closed to the same empty-input digest.
        return hashlib.sha256(b"").hexdigest()

    return hashlib.sha256(completed.stdout).hexdigest()


def _main() -> int:
    """When the .sh is executed directly it prints the hash. Same for us."""
    print(review_gate_hash())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ("review_gate_hash", "working_tree_gate_hash")
