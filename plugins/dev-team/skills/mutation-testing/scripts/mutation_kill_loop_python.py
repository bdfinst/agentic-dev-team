#!/usr/bin/env python3
"""mutation_kill_loop_python.py — deterministic survivor-kill loop for
Python/mutmut, the Python counterpart to ``mutation_kill_loop.py`` (#1357).

mutmut has no project/solution structure to load from a config file the way
Stryker.NET does — a scoped run only needs the source file and a test
command, so there is no config-file abstraction here (unlike
``mutation_kill_loop.py``'s ``LoopConfig``/``stryker-config.json``). Scoring
and survivor extraction reuse ``mutation_report``'s mutmut-junitxml support
(#1357); the two generic (non-.NET) headless-generation helpers —
``strip_code_fences``, ``resolve_model``, ``claude_cli_available``,
``CLAUDE_CLI`` — are imported from ``mutation_kill_headless`` rather than
duplicated, since neither depends on anything C#-specific.

**Generation is a seam, not a mechanism** (same contract as the C# loop):
the loop never decides *what* tests to write — a caller supplies a
``generate`` callable that returns the new pytest function text. The
default (interactive) path is agent-driven: the ``mutation-kill`` agent
calls :func:`run_for_file` directly, passing a ``generate`` hook backed by a
live agent turn. A ``--headless`` CLI mode shells to ``claude --print`` for
unattended (CI) runs.

**Import boundary.** Everything this module reaches for in
``mutation_kill_headless`` is imported explicitly by name in one block below
(``strip_code_fences``, ``resolve_model``, ``claude_cli_available``,
``CLAUDE_CLI``, ``_timeout_from_env``) — never via a module-qualified reach
into a private, underscore-prefixed name at an arbitrary call site. This
keeps every cross-module dependency visible in one place instead of scattered
through the file.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import mutation_kill_headless as _cs_headless
import mutation_report
import mutation_safety_gate

Generator = Callable[[str, list[dict], str, str], str]

# Mirrors mutation_kill_headless.NO_GENERATOR_MESSAGE — pinned so a contract test
# can assert it verbatim.
NO_GENERATOR_MESSAGE = (
    "no test generator available — invoke via the mutation-kill agent "
    "or pass --headless"
)

# Reused verbatim — neither helper is C#-specific. `_timeout_from_env` is
# actually defined in mutation_kill_loop.py and only incidentally re-exported
# by mutation_kill_headless (`from mutation_kill_loop import ... _timeout_from_env
# ...`) — imported here the same explicit, named way as the other three
# rather than reached via `_cs_headless._timeout_from_env` at its call site
# below (#1598/#1584 review, item 9).
strip_code_fences = _cs_headless.strip_code_fences
resolve_model = _cs_headless.resolve_model
claude_cli_available = _cs_headless.claude_cli_available
CLAUDE_CLI = _cs_headless.CLAUDE_CLI
_timeout_from_env = _cs_headless._timeout_from_env

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
# Routed through mutation_kill_loop.py's _timeout_from_env pattern (imported
# above, in the named-import block) rather than a bare magic number, matching
# every other timeout in this codebase — an override is legitimate for a
# large repo whose mutmut-cache lock is held longer than 300s by a slow,
# in-flight concurrent run.
_MUTMUT_CACHE_LOCK_TIMEOUT_S = _timeout_from_env(
    "DEV_TEAM_MUTATION_MUTMUT_LOCK_TIMEOUT_S", 300
)

# 30s matches mutation_kill_loop.py's own _GIT_TIMEOUT (and
# mutation_baseline_reuse.py's _run_git) — near-instant local git operations
# against a repo that's presumably already responsive. Applied to every
# subprocess.run git call in this module (#1598/#1584 review, item 2): none
# of git_revert/git_reset_and_revert/git_commit previously bounded their
# subprocess, so an unbounded git call here could hang forever instead of
# ever reaching the RuntimeError/exit-4 fatal-revert path.
_GIT_TIMEOUT_S = _timeout_from_env("DEV_TEAM_MUTATION_GIT_TIMEOUT_S", 30)

# How often _acquire_mutmut_cache_lock re-checks the lock directory while
# waiting. Small enough to notice a release promptly; large enough not to
# busy-loop.
_MUTMUT_CACHE_LOCK_POLL_INTERVAL_S = 0.1


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
                subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
            except (FileNotFoundError, OSError) as exc:
                raise RuntimeError(f"mutmut run failed to start: {exc}") from exc

            junit = subprocess.run(
                [*prefix, "junitxml"], cwd=cwd, capture_output=True, text=True, check=False
            )
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
# Insert mechanics — detect-or-refuse, never a silent mis-insertion.
# =============================================================================
class InsertionRefused(Exception):
    """Raised when the file isn't in the flat top-level ``def test_*():``
    shape this heuristic supports.

    Unlike the C# loop's "find the class-closing brace" problem, a flat
    pytest module has no enclosing structure to locate — the safe insertion
    point is simply end-of-file, PROVIDED the file already follows that flat
    convention. A file with no top-level ``def test_`` function at all (e.g.
    tests organized as ``class Test...:`` methods) doesn't match this
    convention, and the loop refuses rather than guess.
    """


@dataclass(frozen=True)
class InsertOutcome:
    """Result of attempting to apply generated tests. ``inserted`` is False
    when the file was left untouched; ``reason`` says why."""

    inserted: bool
    reason: str


# A top-level (unindented) pytest test function declaration, capturing the name.
_FUNC_RE = re.compile(r"^def\s+(test_\w+)\s*\(", re.MULTILINE)


def detect_duplicate_functions(test_text: str, new_text: str) -> list[str]:
    """Return the function names in ``new_text`` that already exist in the file."""
    existing = set(_FUNC_RE.findall(test_text))
    incoming = _FUNC_RE.findall(new_text)
    return [name for name in incoming if name in existing]


def append_at_end_of_file(test_file: Path, new_tests: str, text: str) -> None:
    """Append ``new_tests`` to the end of the file, with one blank line of
    separation, and a trailing newline.

    Raises :class:`InsertionRefused` when the file has no existing top-level
    ``def test_*():`` — the flat-module convention this heuristic supports.
    The file is left untouched on refusal.

    ``text`` is the current test-file content, already read by the caller
    (:func:`apply_generated_tests`) — this function performs no read of its
    own. A previous, optional ``test_text=`` shape let a caller pass in
    content that bypassed reading the file's CURRENT state (including this
    function's own refusal-guard check running against stale content rather
    than what's actually on disk) — a real hazard even though no caller
    exploited it. Removing the optional/None-triggered-fallback shape closes
    that off: freshness is now entirely ``apply_generated_tests``'s
    responsibility, which reads immediately before calling this (#1598/#1584
    review, item 7).
    """
    if not _FUNC_RE.search(text):
        raise InsertionRefused(
            f"refusing to insert into {test_file.name}: no top-level "
            "`def test_*():` found — this heuristic supports only the flat "
            "module convention (a class-based test file needs a different "
            "insertion point, not appended at end-of-file)"
        )

    body = new_tests.strip()
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    test_file.write_text(text + separator + body + "\n", encoding="utf-8")


# A deny-list of APIs a test function that merely kills mutants never
# legitimately needs. Scoped to generated *test* text only — never to the
# source-under-test. Same rationale and same category names as
# ``mutation_kill_insert``'s C# counterpart (kept consistent as a stable,
# operator-facing and test-pinned contract) — this is the Python/pytest
# equivalent, guarding this loop's own ``--headless`` unattended-commit path
# against a prompt-injection payload in the mutated source producing
# generated test code with network/filesystem/process side effects that
# would still pass compile+test and get committed with zero human review.
_UNSAFE_PATTERNS: dict[str, re.Pattern[str]] = {
    "network": re.compile(
        r"\b(requests\s*\.|urllib\s*\.\s*request|urllib3\s*\.|httpx\s*\.|socket\s*\.|http\s*\.\s*client)\b"
    ),
    "process": re.compile(
        r"\b(subprocess\s*\.|os\s*\.\s*system|os\s*\.\s*popen|os\s*\.\s*exec\w*|"
        r"os\s*\.\s*(spawn\w*|posix_spawn|fork|forkpty)|Popen)\b"
    ),
    "filesystem": re.compile(
        r"\b(shutil\s*\.\s*rmtree|os\s*\.\s*(remove|unlink))\b"
        r"|\.\s*(write_text|write_bytes|unlink)\s*\("
        r"|open\s*\([^)]*[\"'][waxA]"
    ),
    "environment": re.compile(r"\b(os\s*\.\s*environ|os\s*\.\s*getenv)\b"),
    "reflection": re.compile(r"\b(importlib\s*\.\s*import_module|__import__)\b"),
    "interop": re.compile(r"\b(eval|exec)\s*\(|\bctypes\s*\.|\bpickle\s*\.\s*loads\s*\("),
}


def scan_for_unsafe_patterns(new_tests: str) -> list[str]:
    """Return the category names of any unsafe pattern found in generated text.

    A non-empty result refuses insertion outright — this deny-list is
    deliberately conservative for *generated test* code specifically (a
    legitimate mutant-killing test never needs network/filesystem/process/env
    access), so a false positive refuses-and-logs rather than silently
    inserting unreviewed code. Delegates to :mod:`mutation_safety_gate`,
    shared with :mod:`mutation_kill_insert`, so a future bypass fix or new
    category lands once for both languages.
    """
    return mutation_safety_gate.scan_for_unsafe_patterns(new_tests, _UNSAFE_PATTERNS)


def apply_generated_tests(test_file: Path, new_tests: str) -> InsertOutcome:
    """Insert generated tests, guarding duplicates and unsafe structure.

    Returns an :class:`InsertOutcome`; the file is only ever written on the
    ``inserted=True`` path. Empty generation, an unsafe pattern, duplicate
    function names, and a refused insert all leave the file untouched.

    Reads ``test_file`` exactly once here — immediately before the
    duplicate-name check — and reuses that single fresh read for both the
    check and the write (passed through to :func:`append_at_end_of_file`,
    which performs no read of its own). A prior shape let the caller (e.g.
    ``run_for_file``) thread in its OWN already-read ``test_text`` for the
    duplicate check — but that text was read *before* the possibly
    multi-minute ``generate()`` call, so the check ran against a stale
    snapshot: a function name added to the file during generation (by
    another process, or a second concurrent round) would go undetected as a
    duplicate. Reading fresh here, after ``generate()`` has already
    returned, closes that gap (#1598/#1584 review, item 7).
    """
    if not new_tests.strip():
        return InsertOutcome(False, "no tests generated")

    unsafe_categories = scan_for_unsafe_patterns(new_tests)
    if unsafe_categories:
        return InsertOutcome(False, f"refused — unsafe pattern(s): {unsafe_categories}")

    text = test_file.read_text(encoding="utf-8")

    dupes = detect_duplicate_functions(text, new_tests)
    if dupes:
        return InsertOutcome(False, f"duplicate function names: {dupes}")

    try:
        append_at_end_of_file(test_file, new_tests, text)
    except InsertionRefused as exc:
        return InsertOutcome(False, str(exc))
    return InsertOutcome(True, "inserted")


# =============================================================================
# Verify / commit / revert.
# =============================================================================
def python_compiles(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Syntax-check the test file — Python's equivalent of a build step."""
    rc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(test_file)],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    ).returncode
    return rc == 0


def run_scoped_pytest(test_file: Path, *, cwd: Path | None = None) -> bool:
    """Run the test file under pytest. False on any non-zero exit."""
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    ).returncode
    return rc == 0


def git_revert(
    test_file: Path, *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> bool:
    """Discard working-tree changes to one file (``git checkout -- <file>``).

    Returns True on a successful revert, False on a non-zero exit or a
    timeout — mirrors ``mutation_kill_loop.py``'s ``git_revert`` (#1598):
    callers can no longer mistake a failed/timed-out revert for a successful
    one. ``run_scoped_mutmut``'s always-revert ``finally`` cleanup calls this
    too but, matching its pre-existing best-effort contract, does not inspect
    the return value — only ``run_for_file``'s build/test/commit-failure
    paths (below) do.

    ``env`` defaults to ``None`` (inherit the ambient environment); tests
    pass a scrubbed env so this real git subprocess can't be redirected by
    an inherited ``GIT_DIR``/``GIT_WORK_TREE`` (#1598/#1584 review, item 4
    follow-up).
    """
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", "checkout", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=_GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git checkout reverting {test_file} timed out after "
            f"{_GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    return result.returncode == 0


def git_reset_and_revert(
    test_file: Path, *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> bool:
    """Unstage AND restore ``test_file`` — the correct revert after a FAILED
    commit specifically. Mirrors ``mutation_kill_loop.py``'s
    ``git_reset_and_revert`` (#1598/#1584 review).

    ``git_commit`` runs ``git add -- <test_file>`` before attempting the
    commit. If the commit itself then fails, ``test_file`` is left staged
    with the mutated content — a plain ``git checkout -- <file>`` (what
    :func:`git_revert` does) restores the working tree **from the index**,
    which still holds the mutation. This unstages first
    (``git reset -q HEAD -- <file>``) so HEAD, the index, and the working
    tree all agree afterward. Returns True only if both steps succeed —
    including on a timeout of either step.
    """
    try:
        reset_result = subprocess.run(
            ["git", "--literal-pathspecs", "reset", "-q", "HEAD", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=_GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git reset unstaging {test_file} timed out after "
            f"{_GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    if reset_result.returncode != 0:
        return False
    return git_revert(test_file, cwd=cwd, env=env)


def git_commit(
    message: str,
    test_file: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Stage and commit only ``test_file``. Returns True on a successful
    commit; False on a non-zero exit or a timeout of either step."""
    # `--` guards against a test_file path that happens to start with `-`
    # being parsed as a git flag instead of a path — mirrors the C# loop's
    # git_commit and the adjacent `git checkout --` above (#1584).
    # `--literal-pathspecs` (right after `git`, #1598/#1584 review, item 5)
    # forces every pathspec argument below to be treated as a literal path,
    # not a pathspec: `--` alone does NOT disable pathspec magic (`:/`,
    # `:(exclude)`, `:!`, etc.) for the argument that follows it.
    try:
        subprocess.run(
            ["git", "--literal-pathspecs", "add", "--", str(test_file)],
            cwd=cwd,
            check=False,
            timeout=_GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git add for {test_file} timed out after "
            f"{_GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    try:
        commit_result = subprocess.run(
            ["git", "--literal-pathspecs", "commit", "-m", message, "--", str(test_file)],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            timeout=_GIT_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: git commit for {test_file} timed out after "
            f"{_GIT_TIMEOUT_S}s (set DEV_TEAM_MUTATION_GIT_TIMEOUT_S to "
            "raise it)\n"
        )
        return False
    return commit_result.returncode == 0


def _commit_message(
    round_num: int,
    source_file: str,
    survivors: int,
    new_tests: str,
    *,
    generator_label: str | None = None,
) -> str:
    count = len(_FUNC_RE.findall(new_tests))
    message = (
        f"test(mutation): kill round {round_num} — {source_file}\n\n"
        f"{count} new test(s) targeting {survivors} surviving mutant(s)"
    )
    return mutation_safety_gate.append_generator_trailer(message, generator_label)


def _revert_or_raise(
    test_file: Path, cwd: Path | None, reason: str, *, after_commit: bool = False
) -> None:
    """Revert ``test_file``, raising if the revert itself fails.

    ``after_commit=True`` routes through :func:`git_reset_and_revert`
    (unstage + checkout), not plain :func:`git_revert` — ``git_commit``
    already staged ``test_file`` before the commit attempt failed, so a
    plain checkout alone would restore from that still-mutated index, not
    HEAD (#1598/#1584 review). A revert that itself fails is fatal: it
    leaves the working tree in an unknown, possibly-mutated state, so this
    raises rather than letting the loop continue silently.

    Hoisted to module level — explicit params, not a closure capturing
    ``test_file``/``cwd`` from an enclosing scope — to mirror
    ``mutation_kill_loop.py``'s ``_revert_or_raise`` shape and make this
    independently testable/monkeypatchable (#1598/#1584 review, item 3).
    """
    revert_ok = (
        git_reset_and_revert(test_file, cwd=cwd)
        if after_commit
        else git_revert(test_file, cwd=cwd)
    )
    if not revert_ok:
        raise RuntimeError(
            f"revert failed for {test_file} after {reason} — the "
            "working tree is left in an unknown state (mutated test "
            "content may still be on disk, uncommitted)"
        )


def _verify_and_commit(
    round_num: int,
    source_file: str,
    survivor_count: int,
    new_tests: str,
    *,
    test_file: Path,
    cwd: Path | None,
    log: Callable[[str], None],
    generator_label: str | None,
) -> bool:
    """Compile-check → scoped pytest → commit-on-green / revert-on-failure.

    Returns True on a successful commit, False when the round is abandoned
    (compile failure, test failure, or commit failure — each reverted via
    :func:`_revert_or_raise`, which raises if the revert itself fails).

    Mirrors ``mutation_kill_loop.py``'s ``_verify_and_commit`` extraction —
    pulled out of ``run_for_file`` so the build/verify/commit/revert
    sequence is independently testable/monkeypatchable with explicit params
    instead of living inline in a ~140-line function (#1598/#1584 review,
    item 3).
    """
    if not python_compiles(test_file, cwd=cwd):
        log("  compile check failed — reverting")
        _revert_or_raise(test_file, cwd, "a failed compile check")
        return False
    if not run_scoped_pytest(test_file, cwd=cwd):
        log("  tests failed — reverting")
        _revert_or_raise(test_file, cwd, "a failed test run")
        return False

    log("  green — committing")
    committed = git_commit(
        _commit_message(
            round_num,
            source_file,
            survivor_count,
            new_tests,
            generator_label=generator_label,
        ),
        test_file,
        cwd=cwd,
    )
    if not committed:
        # A failed commit is a round failure, not a silent success —
        # without this check the loop would advance believing this
        # round landed, while the new tests sit uncommitted (and
        # possibly still staged) on disk (#1598).
        log("  commit failed — reverting")
        _revert_or_raise(test_file, cwd, "a failed commit", after_commit=True)
        return False
    return True


# =============================================================================
# Per-file loop — run → score → check → generate → insert → verify → commit.
# =============================================================================
def run_for_file(
    source_file: str,
    *,
    test_file: Path,
    source_path: Path,
    test_command: str,
    generate: Generator,
    max_rounds: int = 5,
    initial_junitxml: str | None = None,
    cwd: Path | None = None,
    log: Callable[[str], None] = print,
    generator_label: str | None = None,
) -> None:
    """Drive the deterministic survivor-kill loop for one Python source file.

    ``generate`` is the sole non-deterministic step: given survivors +
    context it returns the raw new-test text. Everything else — scoped run,
    scoring, duplicate/insert guards, compile/test verification,
    revert-on-failure, commit-on-green, and the no-improvement stop — is
    mechanical, mirroring :func:`mutation_kill_loop.run_for_file`'s contract.
    ``generator_label``, when set, is recorded in the commit message as an
    audit trail (e.g. distinguishing an unattended ``--headless`` commit from
    an agent-driven one).

    A failed revert (after a compile failure, a test failure, or a failed
    commit) is fatal: it raises :class:`RuntimeError` rather than returning
    silently, because a revert that can't be verified as having succeeded
    means the working tree is left in an unknown, possibly-mutated state
    (#1598). A failed commit itself is also a round failure, not a silent
    success: it is reverted (unstage + restore, via
    :func:`git_reset_and_revert`) and the round stops without advancing.
    """
    prev_survivors: int | None = None

    for round_num in range(1, max_rounds + 1):
        if initial_junitxml is not None and round_num == 1:
            junitxml_text = initial_junitxml
        else:
            junitxml_text = run_scoped_mutmut(
                source_file, test_command=test_command, test_file=test_file, cwd=cwd
            )

        survivors = extract_survivors(junitxml_text, source_file)
        survivor_count = len(survivors)
        summary = mutation_report.score_mutmut_junitxml(junitxml_text)
        log(
            f"  round {round_num}: honest={summary.honest_score:.1f}% "
            f"survivors={survivor_count}"
        )

        total_mutants = (
            summary.killed + summary.survived + summary.timeout + summary.no_coverage
        )
        if total_mutants == 0:
            log(
                "  zero mutants generated — this is NOT convergence. mutmut "
                "produced no results at all (a real internal crash — e.g. "
                "the known Python 3.13+ pickle incompatibility, 'TypeError: "
                "cannot pickle itertools.count object' — or a file with no "
                "executable statements). Stopping without declaring "
                "survivors == 0 (#1359)."
            )
            return
        if survivor_count == 0:
            log("  no survivors — done")
            return
        if prev_survivors is not None and survivor_count >= prev_survivors:
            log("  no improvement this round — stopping")
            return
        prev_survivors = survivor_count

        # Read once and thread the text through the generation prompt and
        # the duplicate check below — apply_generated_tests reads the file
        # at most once here instead of re-reading it a second time for that
        # same purpose (#1584). This snapshot is NOT threaded into the
        # actual insert-and-write step: generate() is an LLM call that can
        # run for minutes, so using this pre-generation snapshot as the
        # write base afterward would widen a microseconds-wide
        # read-before-write race into a multi-minute one. append_at_end_of_file
        # (inside apply_generated_tests) does its own fresh read immediately
        # before writing instead (#1598/#1584 review).
        test_text = test_file.read_text(encoding="utf-8")
        new_tests = generate(
            source_file,
            survivors,
            source_path.read_text(encoding="utf-8"),
            test_text,
        )

        # No test_text= here on purpose (#1598/#1584 review, item 7):
        # apply_generated_tests always does its own fresh read now, shared
        # between its duplicate-name check and the write — this pre-generation
        # `test_text` snapshot (read above, before the possibly multi-minute
        # `generate()` call) is only for the generation prompt.
        outcome = apply_generated_tests(test_file, new_tests)
        if not outcome.inserted:
            log(f"  not inserted ({outcome.reason}) — stopping")
            return

        if not _verify_and_commit(
            round_num,
            source_file,
            survivor_count,
            new_tests,
            test_file=test_file,
            cwd=cwd,
            log=log,
            generator_label=generator_label,
        ):
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
    model: str | None = None, *, cwd: Path | None = None
) -> Generator:
    """Return a :data:`Generator` that shells to ``claude --print``.

    Identical contract to ``mutation_kill_headless.make_headless_generator``, but
    with the Python-flavored prompt above.
    """

    def generate(
        source_file: str,
        survivors: list[dict],
        source_text: str,
        test_text: str,
    ) -> str:
        prompt = build_generation_prompt(source_file, survivors, source_text, test_text)
        cmd = [CLAUDE_CLI, "--print"]
        if model:
            cmd += ["--model", model]
        cmd.append(prompt)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return strip_code_fences(result.stdout)

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

    try:
        run_for_file(
            args.file,
            test_file=Path(args.test_file),
            source_path=Path(args.source_path),
            test_command=args.test_command,
            generate=make_headless_generator(model),
            max_rounds=args.max_rounds,
            generator_label=f"headless ({model or 'default'})",
        )
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
