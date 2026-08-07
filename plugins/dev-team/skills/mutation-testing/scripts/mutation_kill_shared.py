#!/usr/bin/env python3
"""mutation_kill_shared.py — cross-language loop mechanics shared verbatim
between ``mutation_kill_loop.py`` (C#/Stryker.NET) and
``mutation_kill_loop_python.py`` (Python/mutmut) (#1583).

Pieces were hand-duplicated between the two loops with identical behavior —
not just similar, identical argv shapes, identical error messages, identical
timeout semantics — before this module existed:

- ``_timeout_from_env`` — the env-var-driven timeout parser both loops (and
  the headless-generation timeouts below) rely on.
- ``git_revert`` / ``git_reset_and_revert`` / ``git_commit`` — discard,
  unstage-then-discard, and stage-then-commit exactly one test file, under a
  bounded timeout with the ``--literal-pathspecs``/``--`` pathspec guards
  hardened in #1598/#1599.
- ``stop_reason`` — the "zero survivors, or no improvement over the previous
  round" predicate that ends a file's kill loop.
- ``resolve_model`` / ``strip_code_fences`` / ``claude_cli_available`` /
  ``CLAUDE_CLI`` / ``run_claude_headless`` (moved here from
  ``mutation_kill_headless.py`` in #1601) — the ``claude --print`` invocation
  glue neither loop's scoring/insertion/orchestration logic actually needs,
  but that ``mutation_kill_loop_python.py`` previously reused by importing
  ``mutation_kill_headless.py`` at module scope. That module is NOT a neutral
  one — it imports ``mutation_kill_loop`` (the C#/Stryker.NET loop) and owns
  the C#-only ``--config``/``--stryker-bin`` CLI surface — so importing it
  from the Python loop transitively pulled in the entire C# stack just to
  reuse five language-neutral names. Both loops now import these directly
  from here instead.
- ``InsertOutcome`` / ``InsertionRefused`` (moved here from
  ``mutation_safety_gate.py`` in #1602) — neither is a safety concept
  (``mutation_safety_gate.py`` is scoped to the unattended-commit
  prompt-injection threat model); they're the plain, framework-agnostic
  result/exception shape both loops' insertion mechanics
  (``mutation_kill_insert.py``, ``mutation_kill_insert_python.py``) return,
  identical in shape between the two languages.
The retry-then-downgrade policy on repeated headless-generation failures
(``is_gateway_class_error``, ``make_retrying_headless_call``,
``GenerationExhausted``, ``DowngradeEvent``, ``make_downgrade_audit_hook``,
#1908) lives in ``mutation_kill_retry.py`` instead — extracted out of this
module (#1925) once it grew into a five-concern grab-bag; that module's only
dependency on this one is ``run_claude_headless``/``resolve_fallback_model``.

Centralizing the pieces below here means a future hardening fix lands once instead of
drifting between two copies (the exact drift risk #1598/#1599 already
demonstrated in practice). Language-specific scoring, insertion mechanics,
and round orchestration stay in each loop's own module.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
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

    ``mutation_kill_loop_python.py``'s ``run_scoped_mutmut`` always-revert
    ``finally`` cleanup calls this too but, matching its pre-existing
    best-effort contract, deliberately does not inspect the return value —
    that path reverts opportunistically on the way out regardless of outcome,
    unlike ``run_for_file``'s build/test/commit-failure paths below, which
    treat a failed revert as fatal.
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

    Both loops call this specifically on the after-a-failed-commit path
    (``_revert_or_raise(..., after_commit=True)``); a build failure or test
    failure calls plain :func:`git_revert` instead — their index already
    equals HEAD in that case (nothing was ever staged), so there's no reason
    to pay the extra ``git reset`` subprocess.
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


# =============================================================================
# Headless generation glue — shelling to `claude --print`. Moved here from
# mutation_kill_headless.py (#1601): both mutation_kill_headless.py (the
# C# CLI) and mutation_kill_loop_python.py (the Python loop) reuse this
# verbatim; neither loop's own scoring/insertion/orchestration logic is
# C#- or Python-specific here.
# =============================================================================

# Timeout for the `claude --print` generation subprocess. Overridable via env
# var since a legitimately slow/large prompt may need a larger budget than
# this default — unlike the 30s used by this module's git-shelling helpers
# above, this subprocess routinely runs for tens of seconds to minutes.
CLAUDE_GENERATION_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S", 300)

# Timeout for the `claude --version` availability probe — small, since it's a
# startup check, not a generation call.
CLAUDE_VERSION_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_VERSION_TIMEOUT_S", 30)

# The Claude CLI binary. Overridable via CLAUDE_BIN so a non-PATH install can
# be pointed at without editing this module.
CLAUDE_CLI = os.environ.get("CLAUDE_BIN", "claude")


def resolve_model(explicit: str | None = None) -> str | None:
    """Resolve the generation model: ``--model`` > ``DEV_TEAM_MUTATION_MODEL``
    > ``None``. When ``None``, ``--model`` is omitted from the ``claude --print``
    invocation and the Claude CLI uses its own default — the plugin never pins a
    model snapshot id in source (models are resolved dynamically, not literalized;
    see ``tests/repo/test_no_pinned_snapshots.py``, the enforcing authority for
    that rule)."""
    if explicit:
        return explicit
    return os.environ.get("DEV_TEAM_MUTATION_MODEL") or None


# One-step model-downgrade ladder (#1908): opus -> sonnet -> haiku -> floor.
# No ``None`` entry: resolve_model()'s "unspecified, let the CLI pick its own
# default" result has no observable ladder position from this codebase (the
# CLI's actual default model is not knowable here), so treating it as
# equivalent to "opus" would be an unverified assumption. ``.get()`` returning
# ``None`` for an unresolved model, the floor (``haiku``), AND any
# operator-supplied model string outside {opus, sonnet, haiku} all mean the
# same thing to this ladder: no known position to step down from. Every round
# before a downgrade is otherwise unaffected: no --model flag is added, no
# snapshot id is pinned (see ``tests/repo/test_no_pinned_snapshots.py``)
# unless/until a downgrade actually happens.
_MODEL_DOWNGRADE_LADDER: dict[str, str] = {
    "opus": "sonnet",
    "sonnet": "haiku",
}

# Mirrors plugins/marketplace-dev/knowledge/agent-contract.json's
# ``model.enum`` minus ``inherit`` (which doesn't make sense as a fallback
# target). ``fable`` is a display-latency variant, not a capability tier, so
# it is a valid --model/DEV_TEAM_MUTATION_FALLBACK_MODEL override value but
# deliberately has no entry in _MODEL_DOWNGRADE_LADDER above — it is not part
# of the opus->sonnet->haiku capability step-down.
_VALID_FALLBACK_MODELS = frozenset({"opus", "sonnet", "haiku", "fable"})


def resolve_fallback_model(current: str | None) -> str | None:
    """Resolve the next model one step down the downgrade ladder from
    ``current``, or the ``DEV_TEAM_MUTATION_FALLBACK_MODEL`` override when
    it names a valid tier.

    ``current`` is expected to be ``resolve_model()``'s result: ``None``,
    ``"opus"``, ``"sonnet"``, or ``"haiku"`` (matched case-insensitively).
    ``None`` (unresolved), ``"haiku"`` (the floor), and any other value not
    on the ladder (an unrecognized model string) all return ``None`` — "no
    known ladder position to step down to." The three cases are
    indistinguishable to ``resolve_fallback_model`` itself; a caller that
    needs to tell them apart for messaging purposes (e.g.
    :func:`_format_downgrade_message`) does so separately, from the
    ``DowngradeEvent`` it already has in hand.

    ``DEV_TEAM_MUTATION_FALLBACK_MODEL``, when set, is checked first and
    wins outright — accepted at ANY ladder position, with no check that it
    is actually a downgrade from ``current``: an explicit operator override
    is authoritative operator intent, not validated against the ladder
    position it replaces (#1908). Matched case-insensitively against
    ``{opus, sonnet, haiku, fable}``. A value outside that enum is never
    silently accepted or silently ignored: it's reported on stderr and this
    call falls back to the one-step ladder default instead.
    """
    override = os.environ.get("DEV_TEAM_MUTATION_FALLBACK_MODEL")
    if override:
        normalized_override = override.strip().lower()
        if normalized_override in _VALID_FALLBACK_MODELS:
            return normalized_override
        sys.stderr.write(
            f"warning: DEV_TEAM_MUTATION_FALLBACK_MODEL={override!r} is not "
            "one of opus/sonnet/haiku/fable — ignoring the override and "
            "using the one-step ladder default instead\n"
        )

    normalized_current = current.strip().lower() if current else None
    return _MODEL_DOWNGRADE_LADDER.get(normalized_current)


_FENCE_OPEN_RE = re.compile(r"^```[\w-]*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```$")


def strip_code_fences(text: str) -> str:
    """Strip one leading and one trailing markdown code fence, if present.

    Claude may wrap generated methods in a ```` ```csharp ```` (or
    ```` ```python ````) block; the loop inserts raw method/test text, so the
    fence is removed on both ends.
    """
    text = _FENCE_OPEN_RE.sub("", text.strip())
    text = _FENCE_CLOSE_RE.sub("", text.strip())
    return text.strip()


class HeadlessCallFailed(RuntimeError):
    """Raised by :func:`run_claude_headless` when ``claude --print`` exits
    non-zero.

    Carries the full, untruncated ``returncode``/``stderr`` as public
    attributes for callers that need to inspect them directly; ``__str__``
    truncates ``stderr`` to 500 bytes to stay byte-for-byte identical to the
    plain ``RuntimeError`` message this type replaces, so any existing
    ``str(exc)``-only consumer (e.g. ``is_gateway_class_error`` in
    ``mutation_kill_retry.py``) is unaffected.
    """

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"claude CLI failed (exit {self.returncode}): {self.stderr[:500]}"


def claude_cli_available() -> bool:
    """True if the Claude CLI responds to ``--version``."""
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_VERSION_TIMEOUT_S,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def run_claude_headless(prompt: str, *, model: str | None, cwd: Path | None = None) -> str:
    """Shell to ``claude --print`` with an already-built ``prompt``; return
    stdout with markdown code fences stripped.

    The single shared invocation glue behind both languages'
    ``make_headless_generator`` factories (#1583). ``--model`` is passed only
    when ``model`` is set; when ``None`` the Claude CLI uses its own default
    (the plugin pins no model snapshot id — see
    ``tests/repo/test_no_pinned_snapshots.py``).

    ``prompt`` is passed over stdin (``input=prompt``), not as a trailing
    argv element (#1607): an argv-passed prompt is both parsed for
    dash-prefixed option injection by the CLI's own arg parser and visible to
    any other process on the host via ``ps``/procfs for the subprocess's
    lifetime — stdin avoids both.
    """
    cmd = [CLAUDE_CLI, "--print"]
    if model:
        cmd += ["--model", model]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            timeout=CLAUDE_GENERATION_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"claude --print generation timed out after "
            f"{CLAUDE_GENERATION_TIMEOUT_S}s (set "
            "DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S to raise it)"
        ) from exc
    if result.returncode != 0:
        raise HeadlessCallFailed(result.returncode, result.stderr)
    return strip_code_fences(result.stdout)


# =============================================================================
# Insertion result shape — shared verbatim between mutation_kill_insert.py
# (C#) and mutation_kill_insert_python.py (Python). Moved here from
# mutation_safety_gate.py (#1602): neither type is a safety concept — that
# module is scoped to the unattended-commit prompt-injection threat model,
# and InsertOutcome/InsertionRefused are returned/raised for plain structural
# refusals too (duplicate names, no methods generated, unrecognized file
# layout).
# =============================================================================
class InsertionRefused(Exception):
    """Raised when a language-specific insertion heuristic can't safely
    locate where to insert generated tests/methods, and refuses rather than
    guess and risk a mis-insertion.

    Framework-agnostic and shared verbatim between ``mutation_kill_insert.py``
    (C# — refuses on a file-scoped namespace or non-4-space class indentation)
    and ``mutation_kill_insert_python.py`` (Python — refuses on a test file
    with no top-level ``def test_*():``) (#1583).
    """


@dataclass(frozen=True)
class InsertOutcome:
    """Result of attempting to apply generated tests/methods to a test file.

    ``inserted`` is False when the file was left untouched; ``reason`` says
    why. Framework-agnostic and shared verbatim between
    ``mutation_kill_insert.py`` and ``mutation_kill_insert_python.py``
    (#1583) — the two languages' insertion heuristics differ, but the result
    shape each reports back to its loop is identical.
    """

    inserted: bool
    reason: str
