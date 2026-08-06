"""hooks/lib/git_safe_diff.py — shared security-pinned `git diff --cached`
flags (#1477, extracted from `pre_commit_review.py`'s `_staged_names()` and
`review_gate_hash.py`'s `review_gate_hash()`).

Both call sites need `git diff --cached` to see the FULL staged changeset —
not a config-narrowed or driver-rewritten view of it. Prior to this module
the two functions hand-duplicated the same security-critical flags, kept in
sync only by comment convention (each function's own docstring cross-
referenced the other's) — exactly the class of gap the #1461 fifth security
re-review had to catch for `--ignore-submodules` on both call sites
separately. A future flag fix applied to one call site and forgotten on the
other is now structurally impossible: there is only one place these flags
are written.

`-c diff.relative=false`: without it, a repo/global `diff.relative=true`
config silently scopes and relativizes `git diff` output to the
invocation's cwd, truncating the result when either hook runs from a
subdirectory.

`--ignore-submodules=none`: the config-only form (`-c
diff.ignoreSubmodules=none`) does NOT suffice — it is overridden by a
per-submodule `submodule.<name>.ignore` (in `.git/config`) OR by an
`ignore` key in a COMMITTED `.gitmodules` file, neither of which needs
local git-config write access (a hostile PR can ship the latter). Only the
command-line option beats both. Without it, a changeset consisting only of
a submodule pointer bump (importing arbitrary third-party code) is either
omitted from `_staged_names()`'s file list entirely, or hashed identically
to no change at all by `review_gate_hash()`.

`--no-color`/`--no-ext-diff`/`--no-textconv` are NOT included here — they
only matter to a caller that reads the diff's rendered CONTENT
(`review_gate_hash()`); `_staged_names()`'s `--name-only` output is
unaffected by diff rendering or textconv drivers, so it never needed them.
Each caller passes its own `extra_flags` for exactly this kind of
caller-specific need; only the flags both call sites actually share live
here.

`target` (#1476): defaults to `"--cached"` (HEAD vs. index — every caller
above needs this and none passed anything else, so the default preserves
their exact original argv). A caller can pass a different comparison —
`target=None` (bare `git diff` — index vs. working tree) or any other ref
expression (e.g. `review_gate_hash.py`'s `branch_diff_gate_hash()`, which
passes `f"{base_ref}...HEAD"`). Same shared safety flags either way — the
vulnerability class (`diff.relative`, submodule-ignore config, external
diff drivers) doesn't care which two trees are being compared.

`review_gate_hash.py`'s `working_tree_gate_hash()` (`target="HEAD"`, added
#1476 for `git commit -a`/pathspec-form-commit detection) was deleted in
#1904 once `pre_commit_review.py` — its sole caller — was retired to a
no-op by #1886's PR-time gate migration; `target`'s generality here is
otherwise unchanged.

Stdlib only.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

# `-c diff.relative=false` must precede the `diff` subcommand — see module
# docstring.
GIT_CONFIG_OVERRIDES = ("-c", "diff.relative=false")

# Must come after the target and any caller-specific extra flags — see
# module docstring for why the command-line form is required.
GIT_IGNORE_SUBMODULES_FLAG = "--ignore-submodules=none"


def run_safe_git_diff(
    extra_flags: Sequence[str],
    cwd: str | Path | None = None,
    text: bool = False,
    target: str | None = "--cached",
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run `git diff [target]` with the shared safety flags, plus
    caller-specific `extra_flags` inserted between the target and the
    trailing `--ignore-submodules=none` — preserves each existing caller's
    original argv order exactly (`_staged_names()`:
    `[..., "--cached", "--name-only", "--ignore-submodules=none"]`;
    `review_gate_hash()`:
    `[..., "--cached", "--no-color", "--no-ext-diff", "--no-textconv",
    "--ignore-submodules=none"]`).

    `target=None` omits the target argument entirely (bare `git diff` —
    index vs. working tree); any other string (`"--cached"`, `"HEAD"`, ...)
    is inserted as-is right after `diff`.

    `timeout` (#1663): seconds to wait before `subprocess.run` raises
    `TimeoutExpired`. Defaults to `None` (wait forever), preserving every
    pre-existing caller's behavior exactly. Only `normalized_gate_hash()`
    passes a value today — it is the one caller that asks git for
    whole-file context (`--unified=100000`), so it is the one caller whose
    runtime scales with repository content rather than with changeset size.
    `TimeoutExpired` propagates to the caller for the same reason a launch
    failure does: this helper builds and runs the safe argv, it does not
    decide what a given caller should do about a slow git.

    Raises on subprocess launch failure — callers keep their own
    try/except around this call, since `_staged_names()` and
    `review_gate_hash()` intentionally differ in how they handle that
    failure (fail-closed `None` vs. a byte-parity empty-input hash); this
    helper only builds and runs the safe argv, it does not decide how a
    launch failure should be reported.
    """
    argv = ["git", *GIT_CONFIG_OVERRIDES, "diff"]
    if target is not None:
        argv.append(target)
    argv.extend(extra_flags)
    argv.append(GIT_IGNORE_SUBMODULES_FLAG)
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        check=False,
        text=text,
        timeout=timeout,
    )


__all__ = ("GIT_CONFIG_OVERRIDES", "GIT_IGNORE_SUBMODULES_FLAG", "run_safe_git_diff")
