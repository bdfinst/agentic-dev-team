#!/usr/bin/env python3
"""mutation_kill_loop_python.py — deterministic survivor-kill loop for
Python/mutmut, the Python counterpart to ``mutation_kill_loop.py`` (#1357).

mutmut has no project/solution structure to load from a config file the way
Stryker.NET does — a scoped run only needs the source file and a test
command, so there is no config-file abstraction here (unlike
``mutation_kill_loop.py``'s ``LoopConfig``/``stryker-config.json``). Scoring
and survivor extraction reuse ``mutation_report``'s mutmut-junitxml support
(#1357).

**Generation is a seam, not a mechanism** (same contract as the C# loop):
the loop never decides *what* tests to write — a caller supplies a
``generate`` callable that returns the new pytest function text. The
default (interactive) path is agent-driven: the ``mutation-kill`` agent
calls :func:`run_for_file` directly, passing a ``generate`` hook backed by a
live agent turn. A ``--headless`` CLI mode shells to ``claude --print`` for
unattended (CI) runs.

**Scope (#1583).** This module owns the scoped ``mutmut run``,
verify/commit/revert, and ``run_for_file`` orchestration — mirroring
``mutation_kill_loop.py``'s post-#1562 scope exactly. Insertion mechanics
(detect-or-refuse end-of-file test-function appending) live in
``mutation_kill_insert_python.py``, a stdlib-only leaf this module imports
from — never the reverse — mirroring the C# split
(``mutation_kill_insert.py``). Headless generation's shared ``claude --print``
invocation glue and the generic (non-language-specific) helpers
(``strip_code_fences``, ``resolve_model``, ``claude_cli_available``,
``CLAUDE_CLI``, ``run_claude_headless``) live in ``mutation_kill_shared.py``
(#1601) and are reused, not duplicated, here — only the Python-flavored
prompt (``build_generation_prompt``/``build_survivor_summary``) and the
``--headless`` CLI argument parsing for THIS loop stay local, since mutmut's
CLI args (``--test-command``, no ``--config``/``--stryker-bin``) genuinely
differ from the C# loop's.

**Shared mechanics (#1583).** ``_timeout_from_env``, ``git_revert``,
``git_reset_and_revert``, ``git_commit``, and the "no improvement across
rounds" stop predicate are imported from ``mutation_kill_shared.py`` rather
than defined here — they were byte-for-byte duplicated with
``mutation_kill_loop.py`` before that module existed.

**Import boundary (#1601).** ``resolve_model``, ``claude_cli_available``,
``CLAUDE_CLI``, and ``run_claude_headless`` are imported directly from
``mutation_kill_shared`` — never from ``mutation_kill_headless``, which is
the C#/Stryker.NET CLI module (it imports ``mutation_kill_loop`` at module
scope and owns the C#-only ``--config``/``--stryker-bin`` CLI surface).
(``strip_code_fences`` also moved to ``mutation_kill_shared`` but isn't
imported here directly — this module only reaches it indirectly, through
``run_claude_headless``'s own internal call.) Reaching into
``mutation_kill_headless`` for these language-neutral names used to
transitively pull the entire C# stack into this Python-only loop; importing
them from the neutral ``mutation_kill_shared`` module instead removes that
coupling entirely.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# typing, not collections.abc: the `Generator` alias below is a real runtime
# expression, so `from __future__ import annotations` cannot defer it — it
# must be subscriptable at import time. collections.abc generics have been
# since 3.9, which the 3.10 floor (ADR 0031) clears.
import mutation_report
import mutation_safety_gate
from mutation_kill_insert_python import apply_generated_tests, count_tests
from mutation_kill_shared import (
    CLAUDE_CLI,
    EXIT_GENERATION_EXHAUSTED,
    GIT_TIMEOUT_S,  # noqa: F401 — re-exported for tests (loop.GIT_TIMEOUT_S), matching the C# sibling's export name
    DowngradeEvent,
    GenerationExhausted,
    _timeout_from_env,
    claude_cli_available,
    git_commit,
    git_reset_and_revert,
    git_revert,
    make_downgrade_audit_hook,
    make_retrying_headless_call,
    resolve_model,
    run_claude_headless,  # noqa: F401 — re-exported for tests (loop.run_claude_headless identity check); make_headless_generator now calls it indirectly via make_retrying_headless_call (#1908)
    stop_reason,
)

Generator = Callable[[str, list[dict], str, str], str]

# Mirrors mutation_kill_headless.NO_GENERATOR_MESSAGE — pinned so a contract test
# can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

MISSING_CLAUDE_MESSAGE = (
    f"--headless requires the Claude CLI but '{CLAUDE_CLI}' is not available. "
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`) and "
    "authenticate it (run `claude` once to log in, or set ANTHROPIC_API_KEY) — "
    "or set CLAUDE_BIN to the CLI's path."
)


# =============================================================================
# Scoped mutmut run — mutmut has no native JSON report; junitxml is it.
# =============================================================================
def _mutmut_argv() -> list[str]:
    """Return the argv prefix for invoking mutmut — `mutmut` or `python3 -m mutmut`."""
    if shutil.which("mutmut") is not None:
        return ["mutmut"]
    return [sys.executable, "-m", "mutmut"]


# Bounds how long a caller waits to acquire the `.mutmut-cache` lock before
# giving up loudly rather than hanging forever behind a stuck/crashed holder.
# An override is legitimate for a large repo whose mutmut-cache lock is held
# longer than 300s by a slow, in-flight concurrent run.
_MUTMUT_CACHE_LOCK_TIMEOUT_S = _timeout_from_env(
    "DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", 300
)

# How often _acquire_mutmut_cache_lock re-checks the lock directory while
# waiting. Small enough to notice a release promptly; large enough not to
# busy-loop.
_MUTMUT_CACHE_LOCK_POLL_INTERVAL_S = 0.1

# Timeouts for the mutmut subprocesses themselves (#1605) — previously
# unbounded, unlike the C# loop's DOTNET_BUILD_TIMEOUT_S/DOTNET_TEST_TIMEOUT_S
# equivalents. The scoped `mutmut run` mutates and re-tests every mutant for
# one file, so its budget mirrors STRYKER_RUN_TIMEOUT_S's order of magnitude;
# `mutmut junitxml` only reformats already-computed results, so it gets a
# short budget instead.
_MUTMUT_RUN_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_MUTMUT_TIMEOUT_S", 3600)
_MUTMUT_JUNITXML_TIMEOUT_S = _timeout_from_env(
    "DEV_TEAM_MUTATION_MUTMUT_JUNITXML_TIMEOUT_S", 60
)


def _acquire_mutmut_cache_lock(root: Path, *, timeout: float = _MUTMUT_CACHE_LOCK_TIMEOUT_S) -> Path:
    """Acquire a simple, cross-platform mutex directory guarding
    ``.mutmut-cache`` for the duration of one scoped mutmut run (#1584).

    Two concurrent ``run_scoped_mutmut`` invocations sharing the same repo
    race on the single, fixed ``.mutmut-cache`` path — one run's cache
    delete/mutmut-run/revert sequence can corrupt or invalidate another's
    in-flight run. ``Path.mkdir()`` is atomic on both POSIX and Windows,
    unlike ``fcntl``/``msvcrt`` file locks (only one of which is available on
    any given platform), so a lock *directory* — created, then removed on
    release — is the portable, stdlib-only mutex.
    """
    lock_dir = root / ".mutmut-cache.lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock_dir.mkdir()
            return lock_dir
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"timed out after {timeout}s waiting for the .mutmut-cache "
                    f"lock at {lock_dir} — a concurrent run may be stuck "
                    "holding it (remove the directory manually to recover if "
                    "no run is actually in flight)"
                ) from None
            time.sleep(_MUTMUT_CACHE_LOCK_POLL_INTERVAL_S)


def _release_mutmut_cache_lock(lock_dir: Path) -> None:
    """Release the lock directory acquired by :func:`_acquire_mutmut_cache_lock`.

    Called from a ``finally`` block — swallows ``OSError``/``FileNotFoundError``
    (e.g. the directory was already removed) so a release-time failure never
    masks whatever exception the run itself was raising (#1598/#1584 review).
    """
    with contextlib.suppress(OSError, FileNotFoundError):
        lock_dir.rmdir()


def run_scoped_mutmut(
    source_file: str,
    *,
    test_command: str,
    test_file: Path | None = None,
    cwd: Path | None = None,
) -> str:
    """Run mutmut scoped to one file; return the ``mutmut junitxml`` output.

    Clears any stale ``.mutmut-cache`` first — a cache from a *different*
    scope (a prior run against another file, or a stale run from before this
    file changed) is silently reused otherwise, which was a real trap hit
    manually while dogfooding this loop by hand (#1354): every run must see
    its own fresh baseline, not a leftover one.

    **Always reverts ``source_file`` (and ``test_file``, when given) in a
    ``finally``.** mutmut mutates the real source file on disk for the
    duration of each mutant's test run and restores it when that mutant
    finishes — but an internal mutmut crash (a real, reproducible one: mutmut
    2.5.1's own cache layer raises ``AssertionError``/``ValueError`` on some
    files, confirmed while dogfooding this exact function against
    ``hooks/mutation_adapters/mutmut.py`` — see #1357) skips that restore
    and leaves the mutated content on disk. Unlike Stryker.NET (which
    instruments a separate build, never the real file), mutmut's crash
    failure mode is "corrupt the file under test," so every scoped run must
    unconditionally `git checkout --` it afterward — succeeding, failing, or
    raising.

    The **test file** the ``--runner`` command exercises is exposed to the
    same failure mode — mutmut 2.5.1 has also been observed to truncate the
    runner's test file to empty via a crashed ``.bak``-restore (#1359),
    which silently breaks the *next* round's baseline (mutmut then reports
    zero mutants — a false "converged" positive, not real coverage). Passing
    ``test_file`` reverts it alongside ``source_file`` in the same
    ``finally``; each round's ``git checkout --`` restores exactly the
    state committed at the end of the previous round, which is always the
    correct baseline for the round about to run.

    **Lock-guarded end to end** (#1584): the cache delete, the mutmut run
    itself, and the revert are all held under ``.mutmut-cache.lock`` — not
    just the delete — because mutmut's cache is shared, fixed-path state for
    the whole repo; a second concurrent invocation reading/writing it
    mid-run is exactly as corrupting as racing the delete alone.
    """
    root = cwd or Path(".")
    lock_dir = _acquire_mutmut_cache_lock(root)
    try:
        (root / ".mutmut-cache").unlink(missing_ok=True)

        prefix = _mutmut_argv()
        argv = [
            *prefix,
            "run",
            f"--paths-to-mutate={source_file}",
            "--runner",
            test_command,
            "--no-progress",
            "--simple-output",
        ]
        try:
            try:
                subprocess.run(
                    argv,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_MUTMUT_RUN_TIMEOUT_S,
                )
            except (FileNotFoundError, OSError) as exc:
                raise RuntimeError(f"mutmut run failed to start: {exc}") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"mutmut run timed out after {_MUTMUT_RUN_TIMEOUT_S}s for "
                    f"{source_file} (set DEV_TEAM_MUTATION_MUTMUT_TIMEOUT_S to "
                    "raise it)"
                ) from exc

            try:
                junit = subprocess.run(
                    [*prefix, "junitxml"],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_MUTMUT_JUNITXML_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "mutmut junitxml extraction timed out after "
                    f"{_MUTMUT_JUNITXML_TIMEOUT_S}s (set "
                    "DEV_TEAM_MUTATION_MUTMUT_JUNITXML_TIMEOUT_S to raise it)"
                ) from exc
            return junit.stdout or ""
        finally:
            git_revert(Path(source_file), cwd=cwd)
            if test_file is not None:
                git_revert(test_file, cwd=cwd)
    finally:
        _release_mutmut_cache_lock(lock_dir)


def extract_survivors(junitxml_text: str, source_file: str) -> list[dict]:
    """Return the surviving mutants for one source file (flattened).

    Delegates parsing to :func:`mutation_report.survivors_from_mutmut_junitxml`
    — mutmut names no per-mutation operator, so every survivor's
    ``mutatorName`` is the fixed literal ``"mutmut"`` (a single group).
    """
    grouped = mutation_report.survivors_from_mutmut_junitxml(
        junitxml_text, source_file
    )
    return [mutant for mutants in grouped.values() for mutant in mutants]


# =============================================================================
# Verify — python_compiles/run_scoped_pytest go through subprocess here;
# git_revert/git_reset_and_revert/git_commit are imported from
# mutation_kill_shared.py (#1583) rather than defined in this section.
# =============================================================================
# Timeouts for the compile-check and scoped-test subprocesses (#1605) —
# previously unbounded, unlike the C# loop's DOTNET_BUILD_TIMEOUT_S/
# DOTNET_TEST_TIMEOUT_S equivalents.
_PYTHON_COMPILE_TIMEOUT_S = _timeout_from_env(
    "DEV_TEAM_MUTATION_PYTHON_COMPILE_TIMEOUT_S", 600
)
_PYTEST_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_PYTEST_TIMEOUT_S", 600)


def _neutralize_leading_dash(path: Path) -> str:
    """Return ``str(path)`` guarded against being parsed as a CLI flag
    instead of a positional filename (#1607) — a ``test_file`` value like
    ``-p`` would otherwise let pytest interpret it as ``-p <plugin>`` rather
    than a (nonexistent) file. A ``--`` end-of-options marker is the usual
    fix (and is what ``py_compile``'s own ``argparse``-based CLI honors),
    but pytest's own argument parser does NOT treat ``--`` as ending option
    parsing — a flag placed after it is still parsed, not treated as a bare
    positional — so prefixing a relative, dash-leading path with ``./``
    instead, which works regardless of a tool's own ``--`` support.
    """
    text = str(path)
    return f"./{text}" if text.startswith("-") else text


def python_compiles(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Syntax-check the test file — Python's equivalent of a build step.

    False (not raised) on a timeout, matching this function's existing
    "non-zero returncode -> False" contract for a plain compile failure.
    """
    try:
        rc = subprocess.run(
            [sys.executable, "-m", "py_compile", _neutralize_leading_dash(test_file)],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            timeout=_PYTHON_COMPILE_TIMEOUT_S,
        ).returncode
    except subprocess.TimeoutExpired:
        return False
    return rc == 0


def run_scoped_pytest(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Run the test file under pytest. False on any non-zero exit or timeout."""
    try:
        rc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", _neutralize_leading_dash(test_file)],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            timeout=_PYTEST_TIMEOUT_S,
        ).returncode
    except subprocess.TimeoutExpired:
        return False
    return rc == 0


def _commit_message(
    round_num: int,
    source_file: str,
    survivors: int,
    new_tests: str,
    *,
    generator_label: str | None = None,
    label_override: str | None = None,
) -> str:
    count = count_tests(new_tests)
    # Whitespace-collapsed the same way append_generator_trailer sanitizes
    # generator_label (#1607): source_file is caller-supplied, and a value
    # containing a newline could otherwise forge an extra "Generator:"
    # trailer line into the commit message.
    safe_source_file = " ".join(str(source_file).split())
    message = (
        f"test(mutation): kill round {round_num} — {safe_source_file}\n\n"
        f"{count} new test(s) targeting {survivors} surviving mutant(s)"
    )
    return mutation_safety_gate.append_generator_trailer(
        message, generator_label, label_override=label_override
    )


# =============================================================================
# Per-file loop — run → score → check → generate → insert → verify → commit.
# =============================================================================
@dataclass(frozen=True)
class RunContext:
    """The run-shaped inputs to :func:`run_for_file` — what to run, where, and
    how to report progress.

    Bundles the clump that already travels together at every call site
    (``main()`` here and the ``mutation-kill`` agent's own driving code),
    separating "how to run this file" from ``run_for_file``'s own
    ``generate``/``max_rounds`` controls — mirrors
    ``mutation_kill_loop.py``'s ``RunContext`` (#1561/#1583).
    ``generator_label``, when set, is recorded in the commit message as an
    audit trail (e.g. distinguishing an unattended ``--headless`` commit from
    an agent-driven one).

    ``label_override_provider``, when set, is called with no arguments
    before building each round's commit message; a non-``None`` result
    replaces ``generator_label`` for that commit AND every subsequent commit
    in this file (#1908 Step 3.2b) — the seam a model-downgrade event uses to
    record itself in the audit trail without mutating this frozen,
    file-level dataclass. The lifetime is sticky, not per-commit: once a
    downgrade fires at round N, the stored label is never cleared, so every
    later commit in this file also carries the downgrade label (with the
    round number frozen at N, not the commit's own round) — intentional,
    since the downgraded model really does stay in use for the rest of the
    file. ``None`` (the default) leaves today's ``generator_label``-only
    behavior unchanged.
    """

    test_file: Path
    source_path: Path
    test_command: str
    cwd: Path | None = None
    log: Callable[[str], None] = print
    initial_junitxml: str | None = None
    generator_label: str | None = None
    label_override_provider: Callable[[], str | None] | None = None


def _score_round(
    round_num: int,
    source_file: str,
    ctx: RunContext,
    *,
    prev_survivor_count: int | None,
) -> tuple[list[dict], int] | None:
    """Score one round: scoped-run-or-seeded-report → survivor extraction →
    log → stop-checks.

    Returns ``(survivors, survivor_count)`` to continue the round, or
    ``None`` when the file is done — zero mutants generated (not
    convergence — see below), no survivors, or no improvement over the
    previous round.
    """
    if ctx.initial_junitxml is not None and round_num == 1:
        junitxml_text = ctx.initial_junitxml
    else:
        junitxml_text = run_scoped_mutmut(
            source_file, test_command=ctx.test_command, test_file=ctx.test_file, cwd=ctx.cwd
        )

    survivors = extract_survivors(junitxml_text, source_file)
    survivor_count = len(survivors)
    summary = mutation_report.score_mutmut_junitxml(junitxml_text)
    ctx.log(
        f"  round {round_num}: honest={summary.honest_score:.1f}% "
        f"survivors={survivor_count}"
    )

    total_mutants = (
        summary.killed + summary.survived + summary.timeout + summary.no_coverage
    )
    if total_mutants == 0:
        ctx.log(
            "  zero mutants generated — this is NOT convergence. mutmut "
            "produced no results at all (a real internal crash — e.g. "
            "the known Python 3.13+ pickle incompatibility, 'TypeError: "
            "cannot pickle itertools.count object' — or a file with no "
            "executable statements). Stopping without declaring "
            "survivors == 0 (#1359)."
        )
        return None

    reason = stop_reason(survivor_count, prev_survivor_count)
    if reason is not None:
        ctx.log(f"  {reason}")
        return None

    return survivors, survivor_count


def _revert_or_raise(ctx: RunContext, reason: str, *, after_commit: bool = False) -> None:
    """Revert ``ctx.test_file``, raising if the revert itself fails.

    ``after_commit=True`` routes through :func:`git_reset_and_revert`
    (unstage + checkout), not plain :func:`git_revert` — ``git_commit``
    already staged ``ctx.test_file`` before the commit attempt failed, so a
    plain checkout alone would restore from that still-mutated index, not
    HEAD (#1598/#1584 review). A revert that itself fails is fatal: it
    leaves the working tree in an unknown, possibly-mutated state, so this
    raises rather than letting the loop continue silently.

    Explicit params (not a closure) — mirrors ``mutation_kill_loop.py``'s
    ``_revert_or_raise`` shape and makes this independently
    testable/monkeypatchable (#1598/#1584 review, item 3).
    """
    revert_ok = (
        git_reset_and_revert(ctx.test_file, cwd=ctx.cwd)
        if after_commit
        else git_revert(ctx.test_file, cwd=ctx.cwd)
    )
    if not revert_ok:
        raise RuntimeError(
            f"revert failed for {ctx.test_file} after {reason} — the "
            "working tree is left in an unknown state (mutated test "
            "content may still be on disk, uncommitted)"
        )


def _verify_and_commit(
    round_num: int,
    source_file: str,
    survivor_count: int,
    new_tests: str,
    ctx: RunContext,
) -> int | None:
    """Compile-check → scoped pytest → commit-on-green / revert-on-failure.

    Returns ``survivor_count`` on a successful commit, or ``None`` when the
    round is abandoned (compile failure, test failure, or commit failure —
    each reverted via :func:`_revert_or_raise`, which raises if the revert
    itself fails).
    """
    if not python_compiles(ctx.test_file, cwd=ctx.cwd):
        ctx.log("  compile check failed — reverting")
        _revert_or_raise(ctx, "a failed compile check")
        return None
    if not run_scoped_pytest(ctx.test_file, cwd=ctx.cwd):
        ctx.log("  tests failed — reverting")
        _revert_or_raise(ctx, "a failed test run")
        return None

    ctx.log("  green — committing")
    label_override = (
        ctx.label_override_provider() if ctx.label_override_provider is not None else None
    )
    committed = git_commit(
        _commit_message(
            round_num,
            source_file,
            survivor_count,
            new_tests,
            generator_label=ctx.generator_label,
            label_override=label_override,
        ),
        ctx.test_file,
        cwd=ctx.cwd,
    )
    if not committed:
        # A failed commit is a round failure, not a silent success —
        # without this check the loop would advance believing this
        # round landed, while the new tests sit uncommitted (and
        # possibly still staged) on disk (#1598).
        ctx.log("  commit failed — reverting")
        _revert_or_raise(ctx, "a failed commit", after_commit=True)
        return None
    return survivor_count


def _run_round(
    round_num: int,
    source_file: str,
    ctx: RunContext,
    generate: Generator,
    *,
    prev_survivor_count: int | None,
) -> int | None:
    """Run one round: score (via :func:`_score_round`) → generate → insert →
    verify → commit (via :func:`_verify_and_commit`).

    Returns this round's survivor count (to seed the next round's
    no-improvement check), or ``None`` when the file is done.
    """
    scored = _score_round(round_num, source_file, ctx, prev_survivor_count=prev_survivor_count)
    if scored is None:
        return None
    survivors, survivor_count = scored

    # Read once and thread the text through the generation prompt below —
    # apply_generated_tests reads the file again, fresh, immediately before
    # its own duplicate check and write (see its docstring): using a
    # pre-generation snapshot there would widen a microseconds-wide
    # read-before-write race into a multi-minute one, since generate() is an
    # LLM call that can run for minutes (#1598/#1584 review).
    test_text = ctx.test_file.read_text(encoding="utf-8")
    new_tests = generate(
        source_file,
        survivors,
        ctx.source_path.read_text(encoding="utf-8"),
        test_text,
    )

    outcome = apply_generated_tests(ctx.test_file, new_tests)
    if not outcome.inserted:
        ctx.log(f"  not inserted ({outcome.reason}) — stopping")
        return None

    return _verify_and_commit(round_num, source_file, survivor_count, new_tests, ctx)


def run_for_file(
    source_file: str,
    ctx: RunContext,
    *,
    generate: Generator,
    max_rounds: int = 5,
) -> None:
    """Drive the deterministic survivor-kill loop for one Python source file.

    ``generate`` is the sole non-deterministic step: given survivors +
    context it returns the raw new-test text. Everything else — scoped run,
    scoring, duplicate/insert guards, compile/test verification,
    revert-on-failure, commit-on-green, and the no-improvement stop — is
    mechanical, driven one round at a time by :func:`_run_round` — mirroring
    :func:`mutation_kill_loop.run_for_file`'s contract exactly.

    A failed revert (after a compile failure, a test failure, or a failed
    commit) is fatal: it raises :class:`RuntimeError` rather than returning
    silently, because a revert that can't be verified as having succeeded
    means the working tree is left in an unknown, possibly-mutated state
    (#1598). A failed commit itself is also a round failure, not a silent
    success: it is reverted (unstage + restore, via
    :func:`git_reset_and_revert`) and the round stops without advancing.
    """
    prev_survivor_count: int | None = None
    for round_num in range(1, max_rounds + 1):
        prev_survivor_count = _run_round(
            round_num, source_file, ctx, generate, prev_survivor_count=prev_survivor_count
        )
        if prev_survivor_count is None:
            return


# =============================================================================
# Headless generation — shell to `claude --print` for unattended runs.
# =============================================================================
def build_survivor_summary(survivors: list[dict], *, limit: int = 40) -> str:
    """Render surviving mutants as a compact list."""
    lines = []
    for mutant in survivors[:limit]:
        line = mutant.get("location", {}).get("start", {}).get("line", "?")
        lines.append(f"- L{line}")
    if len(survivors) > limit:
        lines.append(f"- … and {len(survivors) - limit} more")
    return "\n".join(lines)


def build_generation_prompt(
    source_file: str,
    survivors: list[dict],
    source_text: str,
    test_text: str,
    *,
    source_limit: int = 8000,
) -> str:
    """Build the generation prompt.

    The existing test file is the *only* pattern — assertion style and
    fixture usage are inferred from it, never hardcoded here (mirrors
    ``mutation_kill_headless.build_generation_prompt``, adapted for pytest's flat
    ``def test_*():`` convention rather than a class/namespace-wrapped one).
    """
    return (
        f"You are adding new pytest test functions that KILL surviving "
        f"mutations in {source_file}.\n\n"
        "Match the existing test file exactly: its imports, assertion style "
        "(plain `assert`, pytest.approx, monkeypatch, etc.), fixtures, and "
        "naming conventions are the pattern to follow. Do not introduce any "
        "library, helper, or convention that does not already appear in it.\n\n"
        f"## Surviving mutations ({len(survivors)})\n"
        f"{build_survivor_summary(survivors)}\n\n"
        f"## Source under test\n{source_text[:source_limit]}\n\n"
        f"## Existing test file (the pattern to match)\n{test_text}\n\n"
        "## Rules\n"
        "1. Return ONLY the new top-level `def test_*():` function(s) — no "
        "class wrapper, no imports, no module-level fixtures.\n"
        "2. Each must run against the helpers/fixtures already in the "
        "existing test file.\n"
        "3. Reuse the existing file's assertion and fixture patterns exactly.\n"
        "4. Match the existing naming convention.\n"
        "5. Do not redeclare fixtures or helpers already present.\n"
        "6. Every assertion must check a specific value — not just that a "
        "call didn't raise.\n"
    )


def make_headless_generator(
    model: str | None = None,
    *,
    cwd: Path | None = None,
    log: Callable[[str], None] = print,
    on_downgrade: Callable[[DowngradeEvent], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Generator:
    """Return a :data:`Generator` that shells to ``claude --print``.

    Builds the Python-flavored prompt above, then delegates everything else
    to :func:`mutation_kill_shared.make_retrying_headless_call` (#1908) —
    the 3-consecutive-gateway-class-failures/1-same-model-retry/at-most-
    once-per-file-downgrade wrapper around
    :func:`mutation_kill_shared.run_claude_headless` (#1583, relocated from
    ``mutation_kill_headless`` in #1601).

    The retry/downgrade state (consecutive-failure counter, model in use,
    whether this file already spent its one downgrade) lives in the
    ``retrying_call`` closure below — constructed once per file, here, never
    at module scope — so a new file's generator always starts fresh at the
    top of the ladder regardless of a prior file's downgrade, and concurrent
    files under ``--all --concurrency`` (each with their own closure) never
    leak state to one another. ``round_num`` is derived from how many times
    THIS closure has been invoked (``_run_round`` calls ``generate`` once per
    round), since the shared :data:`Generator` signature carries no round
    number of its own.

    ``on_downgrade``, when given, is passed straight through to
    :func:`mutation_kill_shared.make_retrying_headless_call`. Building the
    ``on_downgrade``/``get_label_override`` audit-trail pair
    (:func:`mutation_kill_shared.make_downgrade_audit_hook`) is this
    module's own ``main()``'s job now (#1908 review) — this function no
    longer constructs one internally or attaches a
    ``label_override_provider`` attribute to the returned ``generate``;
    ``main()`` has ``get_label_override`` directly in scope and wires it
    into :class:`RunContext` itself, so no attribute-smuggling is needed.
    """
    retrying_call = make_retrying_headless_call(
        initial_model=model, cwd=cwd, log=log, on_downgrade=on_downgrade, sleep=sleep
    )
    round_counter = {"n": 0}

    def generate(
        source_file: str,
        survivors: list[dict],
        source_text: str,
        test_text: str,
    ) -> str:
        round_counter["n"] += 1
        prompt = build_generation_prompt(source_file, survivors, source_text, test_text)
        return retrying_call(prompt, source_file, round_counter["n"])

    return generate


# =============================================================================
# CLI — startup preflight + --headless generation.
# =============================================================================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mutation_kill_loop_python.py",
        description=(
            "Deterministic survivor-kill loop for Python/mutmut. Agent-driven "
            "by default; --headless enables unattended generation via the "
            "Claude CLI."
        ),
    )
    p.add_argument("--file", required=False, help="Source file to target")
    p.add_argument(
        "--test-command",
        default=None,
        help="Scoped pytest command mutmut runs per mutant (required)",
    )
    p.add_argument("--max-rounds", type=int, default=5, help="Max rounds per file")
    p.add_argument(
        "--headless",
        action="store_true",
        help="Unattended generation via `claude --print` (CI runs).",
    )
    p.add_argument(
        "--model",
        help=(
            "Generation model for --headless. Default: DEV_TEAM_MUTATION_MODEL "
            "env var, else omitted so `claude --print` uses its own default."
        ),
    )
    p.add_argument("--test-file", help="Test file to extend (required with --headless)")
    p.add_argument("--source-path", help="Source file under test (required with --headless)")
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — see :func:`mutation_kill_headless.main` for the contract
    this mirrors."""
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    if not args.headless:
        sys.stderr.write(f"error: {NO_GENERATOR_MESSAGE}\n")
        return 1

    model = resolve_model(args.model)

    if not claude_cli_available():
        sys.stderr.write(f"error: {MISSING_CLAUDE_MESSAGE}\n")
        return 3

    if not (args.file and args.test_file and args.source_path and args.test_command):
        sys.stderr.write(
            "error: --headless requires --file, --test-file, --source-path, "
            "and --test-command\n"
        )
        return 2

    on_downgrade, get_label_override = make_downgrade_audit_hook()
    generate = make_headless_generator(model, on_downgrade=on_downgrade)
    try:
        run_for_file(
            args.file,
            RunContext(
                test_file=Path(args.test_file),
                source_path=Path(args.source_path),
                test_command=args.test_command,
                generator_label=f"headless ({model or 'default'})",
                label_override_provider=get_label_override,
            ),
            generate=generate,
            max_rounds=args.max_rounds,
        )
    except GenerationExhausted as exc:
        # This file's retry-then-downgrade budget is fully spent (3
        # consecutive gateway-class failures + 1 same-model retry, at the
        # original model AND at most one fallback tier) — distinct from exit
        # code 4 below, which most commonly means a failed revert (leaving
        # the working tree in an unknown/possibly-mutated state) but
        # currently also absorbs other, actually-clean RuntimeErrors, e.g. a
        # non-gateway-class generation timeout (#1930). A clean exhaustion
        # mutates nothing in the paths this covers: generation precedes
        # insertion within a round, and a prior round's own
        # insertion-revert failure (compile/test/commit paths, via
        # _revert_or_raise) is itself fatal — raised, never swallowed.
        # run_scoped_mutmut's best-effort post-mutmut-crash revert (its
        # own ``finally``) is deliberately NOT checked, so a mutmut-crash
        # leftover is the one on-disk mutation this exit code does not rule
        # out (#1928) — so callers (stryker_shard_pipeline.py's shard driver) can
        # log this file as unfixed and continue to the next file without
        # affecting the run's exit status, instead of aborting the whole
        # shard (#1908 review).
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_GENERATION_EXHAUSTED
    except RuntimeError as exc:
        # A failed revert or a failed-commit round-abandonment raises
        # RuntimeError (#1598) — mirrors mutation_kill_headless.py's main(),
        # fitting the same 1/2/3 exit-code taxonomy with the next unused
        # code rather than letting this either succeed silently (exit 0)
        # or crash with a raw traceback.
        sys.stderr.write(f"error: {exc}\n")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
