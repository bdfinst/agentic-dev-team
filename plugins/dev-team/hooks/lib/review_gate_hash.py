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
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def review_gate_hash(cwd: Path | None = None) -> str:
    """Return the sha256 hex digest of `git diff --cached`, rendered with
    git's own built-in diff engine — cwd-relative and submodule-ignoring
    config, plus any external diff/textconv driver, are all deliberately
    pinned off (#1461 third/fourth/fifth security re-review; see the
    inline comment on each flag below for its specific rationale). This
    is NOT simply `git diff --cached --no-color` under a non-default
    config — that divergence from the literal command text is the point.

    sha256 hex-encoded; empty-input digest (`sha256(b"")`) on git failure.
    """
    try:
        completed = subprocess.run(
            # `-c diff.relative=false` (#1461 third security re-review):
            # without it, a repo/global `diff.relative=true` config
            # silently scopes `git diff` to the invocation's cwd and
            # relativizes its paths — truncating the hashed patch to a
            # subtree when this hook runs from a subdirectory, exactly the
            # kind of cwd-dependent divergence the rest of #1461's hardening
            # was fixed to avoid. Pinning it false makes this call agree
            # with `hooks/pre_commit_review.py`'s `_staged_names()`, which
            # pins the same override for the same reason.
            #
            # `--no-ext-diff --no-textconv` (#1461 FOURTH security
            # re-review, error-severity): without these, a `diff.external`
            # config or a `GIT_EXTERNAL_DIFF` env var replaces git's own
            # diff rendering entirely — including the `diff --git`/`index`
            # headers this hash is computed over. `git config diff.external
            # /usr/bin/true` collapses this function's output to
            # `sha256(b"")` for EVERY changeset, turning `subject_hash`
            # into a CONSTANT: one honest `/code-review`'s genuine,
            # unforged ledger dispatches would then corroborate every
            # subsequent arbitrary changeset within the recency window,
            # defeating the whole subject-binding fix without forging
            # anything. `--no-ext-diff`/`--no-textconv` disable both the
            # config and the env-var form of external diff/textconv
            # drivers.
            #
            # `--ignore-submodules=none` (#1461 FIFTH security re-review —
            # the `-c diff.ignoreSubmodules=none` form tried first does NOT
            # suffice): a `diff.ignoreSubmodules=all` config only sets the
            # DEFAULT for `--ignore-submodules` — it is overridden by a
            # per-submodule `submodule.<name>.ignore` (in `.git/config`) OR
            # by an `ignore` key in a COMMITTED `.gitmodules` file, neither
            # of which needs local git-config write access (a hostile PR
            # can ship the latter). Only the command-line option beats both.
            # Without it, a changeset consisting only of a submodule pointer
            # bump (importing arbitrary third-party code) hashes identically
            # to no change at all.
            [
                "git",
                "-c", "diff.relative=false",
                "diff", "--cached", "--no-color",
                "--no-ext-diff", "--no-textconv", "--ignore-submodules=none",
            ],
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
