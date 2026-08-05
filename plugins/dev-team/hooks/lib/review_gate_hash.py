"""review_gate_hash — single source of truth for the .review-passed gate hash.

Python port of hooks/lib/review-gate-hash.sh (#576 / #572 Cluster B, #193).

The review gate binds to the STAGED CONTENT (the cached patch), not just
the staged file PATHS. Hashing paths alone let a reviewed file's content
change and still commit unreviewed. Hashing `git diff --cached` captures
both which files are staged AND their staged content — so any edit after
review invalidates the gate and forces a re-review.

Both the writer (`/code-review` step 9) and the reader (pre_commit_review)
MUST compute the hash identically. This module IS that shared computation.

Stdlib-only. See docs/python-hook-contract.md.

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

**`EMPTY_DIGEST` must never be treated as a valid subject-hash match
(issue #1904 Bug 1).** `sha256(b"")` is what every function here returns on
git failure OR on a genuinely empty diff — a CONSTANT shared by every such
case, regardless of the real content involved. A caller that compares a
computed hash against stored/ledger evidence as proof of subject-binding
(`hooks/pre_pr_review.py`'s `_hash_verdict`/`_prepare_gate`,
`hooks/agent_dispatch_ledger.py`'s dispatch-stamping) MUST refuse to treat
`EMPTY_DIGEST` as a match — otherwise one honest review's dispatch evidence,
recorded while nothing was staged, would corroborate ANY later PR whose gate
hash also happens to be empty, defeating subject-binding without forging
anything.
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
import subprocess
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from git_safe_diff import run_safe_git_diff

#: The digest `sha256(b"")` produces — the fail-closed value every function
#: in this module returns on git failure OR on a genuinely empty diff. A
#: CONSTANT: never a valid subject-hash match for a consumer that treats a
#: hash match as proof of subject-binding (issue #1904 Bug 1). See the
#: module docstring for the full rationale.
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


def _git_diff_hash(extra_flags, cwd: Path | None, target: str) -> str:
    """Shared computation behind `review_gate_hash()`, `branch_diff_gate_hash()`,
    and (historically) `working_tree_gate_hash()` — differing ONLY in
    `target`. Extracted (issue #1904) after the three were ~95%
    byte-identical copy-paste. Fails closed to `EMPTY_DIGEST` on any git
    launch failure or non-zero exit — see the module docstring for why a
    caller must never treat that value as a valid subject-hash match.
    """
    try:
        completed = run_safe_git_diff(extra_flags, cwd=cwd, text=False, target=target)
    except (FileNotFoundError, OSError):
        # git not installed; the .sh would have `command not found` on stderr
        # and an empty stdout piped through shasum → sha256 of empty input.
        # We return the same empty-input digest to keep byte-parity.
        return EMPTY_DIGEST

    if completed.returncode != 0:
        # `git diff` outside a repo (or against an unresolvable ref) prints
        # to stderr and exits non-0 with empty stdout; the .sh pipes that
        # empty stdout into shasum, yielding the sha256 of empty input.
        # Mirror that.
        return EMPTY_DIGEST

    return hashlib.sha256(completed.stdout).hexdigest()


_DIFF_RENDER_FLAGS = ("--no-color", "--no-ext-diff", "--no-textconv")


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
    `EMPTY_DIGEST` for EVERY changeset, turning `subject_hash` into a
    CONSTANT: one honest `/code-review`'s genuine, unforged ledger
    dispatches would then corroborate every subsequent arbitrary changeset
    within the recency window, defeating the whole subject-binding fix
    without forging anything.

    sha256 hex-encoded; `EMPTY_DIGEST` on git failure OR a genuinely empty
    staged diff — see the module docstring for why a caller must never
    treat that value as a valid subject-hash match.
    """
    return _git_diff_hash(_DIFF_RENDER_FLAGS, cwd, "--cached")


def branch_diff_gate_hash(base_ref: str, cwd: Path | None = None) -> str:
    """Return the sha256 hex digest of `git diff <base_ref>...HEAD` — the
    PR-time gate's binding content (#1886): the WHOLE branch diff against
    its merge-base with `base_ref`, rather than one commit's staged patch
    (`review_gate_hash()`). `git diff A...B` computes the merge-base
    automatically (the same triple-dot semantics `git log A...B` uses), so
    no separate `git merge-base` call is needed.

    Same shared safety flags via `git_safe_diff.run_safe_git_diff`, and the
    same `EMPTY_DIGEST` fallback on any git failure or empty diff, as
    `review_gate_hash()` above — kept in lockstep deliberately; see that
    function's own docstring for the full rationale of each flag and why a
    forgotten fix on one sibling would reopen the subject-binding bypass
    both exist to prevent.
    """
    return _git_diff_hash(_DIFF_RENDER_FLAGS, cwd, f"{base_ref}...HEAD")


def default_base_ref(cwd: Path | None = None) -> str | None:
    """Best-effort resolution of the branch's base ref for
    `branch_diff_gate_hash()` (#1886): the remote's default branch, e.g.
    `"origin/main"`.

    Tries `git symbolic-ref --short refs/remotes/origin/HEAD` first (the
    canonical answer once `git remote set-head origin -a` or an initial
    `git clone` has run); falls back through a fixed candidate list —
    `origin/main`, `origin/master`, `main`, `master` — verified with `git
    rev-parse --verify` so the returned ref actually resolves to a commit in
    THIS repo, never a guess passed through unchecked.

    Never raises. On total failure (no git, no candidate resolves) returns
    `None` (issue #1904 Bug 1) — NOT `"HEAD"`. A caller that fell back to
    `"HEAD"` here would go on to evaluate `git diff HEAD...HEAD`, which
    SUCCEEDS with empty output, hashing to `EMPTY_DIGEST` — a routine state
    (any shallow/single-branch clone with no remote-tracking branch) that
    would otherwise look like an ordinary, passable "empty diff" rather
    than the gate-setup failure it actually is. Every caller MUST treat a
    `None` return as a hard setup failure and refuse to evaluate a diff
    against a non-existent ref — see `hooks/pre_pr_review.py`'s
    `_prepare_gate()`.
    """
    try:
        completed = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    except (FileNotFoundError, OSError):
        pass

    for candidate in ("origin/main", "origin/master", "main", "master"):
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", candidate],
                cwd=str(cwd) if cwd is not None else None,
                capture_output=True,
                check=False,
                text=True,
            )
        except (FileNotFoundError, OSError):
            break
        if completed.returncode == 0:
            return candidate
    return None


def _main() -> int:
    """When the .sh is executed directly it prints the hash. Same for us.

    `--branch-diff` (#1886) prints `branch_diff_gate_hash(default_base_ref())`
    instead — the PR-time gate's hash — so callers (`skills/code-review/SKILL.md`)
    can compute it with a one-line CLI invocation rather than importing this
    module directly.

    When `default_base_ref()` returns `None` (issue #1904 Bug 1 — the base
    ref could not be resolved at all), `--branch-diff` mode prints nothing
    and exits 1 rather than falling back to hashing `HEAD...HEAD` (which
    would silently succeed with `EMPTY_DIGEST`) — a caller capturing this
    via `$(...)` must treat a non-zero exit as a hard failure, not an
    empty-but-valid hash.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--branch-diff":
        base_ref = default_base_ref()
        if base_ref is None:
            return 1
        print(branch_diff_gate_hash(base_ref))
    else:
        print(review_gate_hash())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = (
    "EMPTY_DIGEST",
    "branch_diff_gate_hash",
    "default_base_ref",
    "review_gate_hash",
)
