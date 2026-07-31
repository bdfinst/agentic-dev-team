#!/usr/bin/env python3
"""mutation_kill_shared.py — cross-language loop mechanics shared verbatim
between ``mutation_kill_loop.py`` (C#/Stryker.NET) and
``mutation_kill_loop_python.py`` (Python/mutmut) (#1583).

Three pieces were hand-duplicated between the two loops with identical
behavior — not just similar, identical argv shapes, identical error
messages, identical timeout semantics — before this module existed:

- ``_timeout_from_env`` — the env-var-driven timeout parser both loops (and,
  transitively via ``mutation_kill_headless.py``'s generation timeout) rely on.
- ``git_revert`` / ``git_reset_and_revert`` / ``git_commit`` — discard,
  unstage-then-discard, and stage-then-commit exactly one test file, under a
  bounded timeout with the ``--literal-pathspecs``/``--`` pathspec guards
  hardened in #1598/#1599.
- ``stop_reason`` — the "zero survivors, or no improvement over the previous
  round" predicate that ends a file's kill loop.

Centralizing them here means a future hardening fix lands once instead of
drifting between two copies (the exact drift risk #1598/#1599 already
demonstrated in practice). Language-specific scoring, insertion mechanics,
and round orchestration stay in each loop's own module.

Stdlib-only. Python 3.8+. See ADR 0014.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _timeout_from_env(name: str, default: int) -> int:
    """Parse a positive-integer timeout (seconds) from an env var.

    Fails fast with a message naming the offending env var, rather than the
    bare, unattributed ``ValueError`` a naked ``int(os.environ.get(...))``
    would raise on a malformed override.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be an integer number of seconds, got {raw!r}"
        ) from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive number of seconds, got {value}")
    return value


# 30s — near-instant local git operations against a repo that's presumably
# already responsive. Overridable via env var for a legitimately slow
# repo/filesystem. Shared by both loops (#1583) — previously two separately
# maintained (but identically named and valued) constants.
GIT_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_GIT_TIMEOUT_S", 30)


def git_revert(
    test_file: Path, *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> bool:
    """Discard working-tree changes to one file (``git checkout -- <file>``).

    Returns True on a successful revert, False on a non-zero exit or a
    timeout — callers can no longer mistake a failed/timed-out revert for a
    successful one (#1598); a leftover, uncommitted mutation left on disk
    after a revert *claims* success is exactly the integrity gap this fixes.

    ``env`` defaults to ``None`` (inherit the ambient environment); tests
    pass a scrubbed env so this real git subprocess can't be redirected by
    an inherited ``GIT_DIR``/``GIT_WORK_TREE`` (#1598/#1584 review, item 4
    follow-up).

    Tolerates a ``None`` result from ``subprocess.run`` (in addition to a
    non-zero returncode) as a failure rather than raising — mirrors the old
    C#-loop-only ``_run_with_timeout``-based implementation's behavior
    (pre-#1583), which several existing tests' minimal test doubles
    incidentally depend on (a ``lambda`` whose body is a bare
    ``list.append(...)``/``dict.update(...)`` call returns ``None``, not a
    ``CompletedProcess``).
    """
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", "checkout", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git checkout reverting {test_file} timed out after "
            f"{GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    if result is None:
        return False
    return result.returncode == 0


def git_reset_and_revert(
    test_file: Path, *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> bool:
    """Unstage AND restore ``test_file`` — the correct revert after a FAILED
    commit specifically, distinct from :func:`git_revert`.

    ``git_commit`` runs ``git add -- <test_file>`` *before* attempting the
    commit. If the commit itself then fails, ``test_file`` is left staged
    with the mutated content. A plain ``git checkout -- <file>`` (what
    :func:`git_revert` does) restores the working tree **from the index**,
    which still holds the mutation — so that revert *reports* success while
    the mutated content survives on disk, staged. This is exactly the
    integrity gap #1598 was meant to close. Unstaging first
    (``git reset -q HEAD -- <file>``) before the checkout makes HEAD, the
    index, and the working tree all agree afterward.

    Returns True only if both the unstage step and the restore step succeed.
    """
    try:
        reset_result = subprocess.run(
            ["git", "--literal-pathspecs", "reset", "-q", "HEAD", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git reset unstaging {test_file} timed out after "
            f"{GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    if reset_result is None or reset_result.returncode != 0:
        return False
    return git_revert(test_file, cwd=cwd, env=env)


def git_commit(
    message: str,
    test_file: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Stage and commit only ``test_file``. Returns True on a successful commit.

    Does not inspect ``git add``'s own returncode (only its timeout) — a
    non-timeout ``git add`` failure (e.g. bad pathspec) still falls through
    to attempting the commit, which will then itself fail and report False.

    ``--`` guards against a ``test_file`` path that happens to start with
    ``-`` being parsed as a git flag instead of a path.
    ``--literal-pathspecs`` (right after ``git``) forces every pathspec
    argument below — including this one — to be treated as a literal path,
    not a pathspec: ``--`` alone does NOT disable pathspec magic (``:/``,
    ``:(exclude)``, ``:!``, etc.) for the argument that follows it, so a
    ``test_file`` value containing those characters could otherwise silently
    broaden what a git command actually touches (#1598/#1584 review, item 5).
    """
    try:
        subprocess.run(
            ["git", "--literal-pathspecs", "add", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git add for {test_file} timed out after "
            f"{GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    # Scoped with the same `-- <path>` pathspec as `git add` above: without
    # it, `git commit -m message` commits the *entire* index, not just
    # test_file — silently sweeping in whatever else happens to be staged
    # (#1598).
    try:
        commit_result = subprocess.run(
            ["git", "--literal-pathspecs", "commit", "-m", message, "--", str(test_file)],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            timeout=GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git commit for {test_file} timed out after "
            f"{GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    if commit_result is None:
        return False
    return commit_result.returncode == 0


def stop_reason(survivor_count: int, prev_survivor_count: int | None) -> str | None:
    """Return the human-readable reason a round should stop, or ``None`` to
    continue to generation.

    Shared, byte-for-byte-identical predicate between the two loops (#1583):
    a file is done when zero survivors remain; a round that didn't improve on
    the previous round's survivor count also stops the loop (the "no
    improvement across rounds" guard that prevents chasing the same
    survivors forever).
    """
    if survivor_count == 0:
        return "no survivors — done"
    if prev_survivor_count is not None and survivor_count >= prev_survivor_count:
        return "no improvement this round — stopping"
    return None
