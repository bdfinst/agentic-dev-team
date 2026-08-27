#!/usr/bin/env python3
"""stryker_shard_pipeline.py — sharded Stryker pipeline with timeout-abort.

Migrated from the ACI ``nextgen-test-upgrade-process`` ``stryker-pipeline.py``
and de-hardcoded: nothing repo-specific lives here. Shards are discovered from
``stryker-config.shard-*.json`` files (emitted by ``stryker_shard_setup.py``);
each shard runs Stryker through the shipped ``csharp_stryker_net_wrapper`` and
the per-shard survivor-fix loop is ``mutation_kill_loop`` forced into
``--headless`` mode (the pipeline is unattended — there is no live agent turn).

Compounding worktrees: shards are processed **sequentially**, each in its own
git worktree created from the current ``HEAD``. Because the survivor-fix loop
commits its fixes onto ``HEAD`` before the next shard's worktree is created,
the second shard's worktree already contains the first shard's committed fixes.

Timeout-abort: Stryker output is streamed through the wrapper's line-callback
(added in #1136 Slice 5.1). A ``"N mutants got status Timeout"`` line kills the
Stryker process and marks the shard failed — timeouts are non-deterministic
noise that would otherwise inflate the score, so we refuse to score them.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). The only
non-stdlib imports are the three sibling plugin modules in this same
``scripts/`` directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# typing, not collections.abc: the module-level type aliases below are real
# runtime expressions, so `from __future__ import annotations` cannot defer
# them — they must be subscriptable at import time. collections.abc generics
# have been since 3.9, which the 3.10 floor (ADR 0031) clears.
import csharp_stryker_net_wrapper as wrapper
import mutation_report
from mutation_kill_retry import EXIT_GENERATION_EXHAUSTED

# ── Constants ────────────────────────────────────────────────────────────────

PYTHON = sys.executable
LOOP_SCRIPT = str(Path(__file__).resolve().parent / "mutation_kill_loop.py")

SHARD_GLOB = "stryker-config.shard-*.json"
SHARD_PREFIX = "stryker-config.shard-"
SHARD_SUFFIX = ".json"

# Stryker prints e.g. "5 mutants got status Timeout" once at least one mutant
# times out. A leading non-zero count means real timeouts (never "0 mutants").
# The status word comes from mutation_report's status vocabulary (AC4) — no raw
# literal is retyped here.
TIMEOUT_PATTERN = re.compile(
    rf"[1-9]\d*\s+mutants got status {mutation_report.STATUS_TIMEOUT}"
)

# Conventional C# test-file names paired with a source file's stem.
_TEST_FILE_SUFFIXES = ("Tests.cs", "Test.cs", "Specs.cs", "Spec.cs")


class ShardSetupMissing(Exception):
    """No ``stryker-config.shard-*.json`` files were discovered — the operator
    must run shard setup first. Carries an actionable message."""


class FixOutcome(NamedTuple):
    """``launch_survivor_fix``'s return value (#1951).

    Replaces the previous ``bool`` return plus a mutable ``exhausted``
    out-parameter — extending that pattern with two more per-run outcomes
    (unresolved test files, no report) would have meant threading a fourth
    and fifth mutable accumulator through three function signatures, which
    is the exact command-query smell #1951 flagged. A single typed result
    mirrors :class:`ShardRunResult`'s existing precedent instead.

    ``ok`` is False the moment a launched fix exits any non-zero, non-5 code
    (see ``launch_survivor_fix``'s docstring for the full exit-code
    decoding). ``exhausted``/``unresolved`` carry ``"shard/source"`` entries.
    ``no_report`` is True when the shard had no Stryker report to act on at
    all — no survivor files were even considered.
    """

    ok: bool
    exhausted: list[str]
    unresolved: list[str]
    no_report: bool


class ShardOutcome(NamedTuple):
    """``process_shard``'s return value (#1951).

    ``status`` keeps the three prior string values (``"ok"`` / ``"failed"`` /
    ``"skipped"``). The other three fields are ``launch_survivor_fix``'s
    :class:`FixOutcome` propagated up one level — empty/False for a shard
    that never reached the survivor-fix stage (Stryker itself failed, the
    shard was skipped, or ``--skip-agent`` was set).
    """

    status: str
    exhausted: list[str]
    unresolved: list[str]
    no_report: bool


class ShardRunResult(NamedTuple):
    """``run_all``'s return value.

    A NamedTuple (not a bare tuple) so a future call site can't silently
    transpose fields — access by name, not position. #1951 widened this from
    2 fields (``failed``, ``exhausted``) to 5, so the previous "still
    2-tuple-unpackable" guarantee no longer holds: ``failed, exhausted =
    run_all(...)`` now raises ``ValueError`` (too many values to unpack).
    That guarantee was a bonus of a 2-field type, not a design goal in its
    own right — every internal caller passes ``run_all``'s result straight
    through by field access, so the trade (3 more silently-swallowed
    run-level outcomes made visible) is worth the break.
    """

    failed: list[str]
    exhausted: list[str]
    unresolved: list[str]
    no_report: list[str]
    skipped: list[str]


# ── Small helpers ──────────────────────────────────────────────────────────────


def _safe(v: str) -> str:
    """Whitespace-collapse a caller-supplied value before it lands in a log
    line — same precedent as ``mutation_kill_loop.py``'s and
    ``mutation_kill_loop_python.py``'s ``_commit_message`` (#1607):
    ``source``/``shard`` are survivor-report file paths, not
    operator-supplied, but could theoretically contain a newline that would
    otherwise forge extra log lines."""
    return " ".join(str(v).split())


def ts() -> str:
    """Wall-clock ``HH:MM:SS`` stamp for per-shard progress lines."""
    # Local wall-clock time is the point (a human-readable progress line),
    # not a comparable timestamp — go through UTC-aware then convert back
    # to the system local zone so the value stays tz-aware for DTZ005
    # without changing the displayed (local) hour/minute/second.
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


def shard_config_path(repo_root: Path, shard: str) -> Path:
    return Path(repo_root) / f"{SHARD_PREFIX}{shard}{SHARD_SUFFIX}"


def report_path(out_dir: Path) -> Path:
    return Path(out_dir) / "reports" / "mutation-report.json"


def discover_shards(repo_root: Path) -> list[str]:
    """Return shard slugs from ``stryker-config.shard-*.json``, sorted.

    Raises :class:`ShardSetupMissing` — naming how to generate the configs —
    when none exist, rather than silently processing nothing.
    """
    configs = sorted(Path(repo_root).glob(SHARD_GLOB))
    if not configs:
        raise ShardSetupMissing(
            f"No {SHARD_GLOB} files found in {repo_root}. Run shard setup first: "
            "python3 stryker_shard_setup.py (generates one shard config per "
            "source project)."
        )
    return [c.name[len(SHARD_PREFIX) : -len(SHARD_SUFFIX)] for c in configs]


# ── Timeout-abort callback ─────────────────────────────────────────────────────


def make_timeout_callback(
    timed_out: threading.Event, *, log: Callable[[str], None] = print
) -> Callable[[str], bool]:
    """Return a line-callback for ``wrapper.run_stryker`` that sets
    ``timed_out`` and requests an abort (returns True) on the first Stryker
    timeout line. Every other line is echoed for live progress."""

    def callback(line: str) -> bool:
        sys.stdout.write(line)
        if TIMEOUT_PATTERN.search(line):
            timed_out.set()
            return True
        return False

    return callback


# ── git worktree management ─────────────────────────────────────────────────────


def _git(cmd: Sequence[str], repo_root: Path, check: bool) -> subprocess.CompletedProcess:
    """Run a git command in ``repo_root``.

    ``check`` is deliberately POSITIONAL, not keyword-only. This is the default
    ``GitRunner``, and that alias — ``Callable[[Sequence[str], Path, bool],
    object]`` — is the contract every call site and every test fake already
    implements positionally. Declaring it ``*, check`` here made the production
    default the only implementation that did not satisfy its own alias, so
    every real invocation (any path that does not inject a fake, which is all
    of them: ``main()`` calls ``run_all(...)`` with no ``git_run``) raised
    ``TypeError: _git() takes 2 positional arguments but 3 were given`` (#1953).

    The bug was invisible to the suite precisely because every test injects a
    fake, so the default was never exercised — which is why the regression
    test below calls the real default rather than a fake.
    """
    return subprocess.run(
        list(cmd), cwd=str(repo_root), capture_output=True, check=check
    )


GitRunner = Callable[[Sequence[str], Path, bool], object]


def worktree_add(
    repo_root: Path, path: Path, *, ref: str = "HEAD", git_run: GitRunner | None = None
) -> None:
    """Create a git worktree at ``path`` from ``ref`` (default ``HEAD``).

    A pre-existing worktree at that path is force-removed first so reruns are
    idempotent. Creating from ``HEAD`` is what makes shards compounding: the
    fixes previous shards committed onto ``HEAD`` are already present.
    """
    git_run = git_run or _git
    if Path(path).exists():
        git_run(["git", "worktree", "remove", "--force", str(path)], repo_root, False)
    git_run(["git", "worktree", "add", "--quiet", str(path), ref], repo_root, True)


def worktree_remove(
    repo_root: Path, path: Path, *, git_run: GitRunner | None = None
) -> None:
    git_run = git_run or _git
    git_run(["git", "worktree", "remove", "--force", str(path)], repo_root, False)


# ── Stryker runner (timeout-abort via the wrapper callback) ────────────────────


StrykerRunner = Callable[..., int]


def run_shard_stryker(
    shard: str,
    *,
    repo_root: Path,
    worktree: Path,
    out_dir: Path,
    stryker_bin: str,
    log: Callable[[str], None] = print,
    run_stryker: StrykerRunner | None = None,
) -> bool:
    """Run Stryker for one shard in its worktree. Returns True on success.

    Streams output through ``wrapper.run_stryker``'s line-callback so a timeout
    line kills the process and marks the shard failed — no re-implemented
    streamer (AC4). A non-zero Stryker exit also fails the shard.
    """
    run_stryker = run_stryker or wrapper.run_stryker
    config = shard_config_path(repo_root, shard)
    if not config.exists():
        log(f"ERROR: {config} not found")
        return False

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    logfile = Path(out_dir).parent / f"{shard}.log"

    timed_out = threading.Event()
    rc = run_stryker(
        stryker_bin=stryker_bin,
        stryker_args=["--config-file", str(config), "--output", str(out_dir)],
        logfile=logfile,
        line_callback=make_timeout_callback(timed_out, log=log),
        cwd=worktree,
    )

    if timed_out.is_set():
        log(
            f"[{ts()}] Shard ABORTED (timeout): {shard} — increase "
            "additional-timeout or reduce concurrency, then retry with "
            "stryker_timeout_retry.py"
        )
        return False
    if rc != 0:
        log(f"[{ts()}] Shard FAILED: {shard} (exit {rc})")
        return False
    return True


# ── Survivor-fix launch (forced --headless) ─────────────────────────────────────


def survivor_source_files(report: Path) -> list[str]:
    """Return the source-file keys in the report that have Survived mutants.

    Report parsing and the ``Survived`` status vocabulary live in
    ``mutation_report`` (AC4) — this never re-walks the report itself.
    """
    return mutation_report.files_with_survivors(report)


def shard_test_projects(config_path: Path) -> list[str]:
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    inner = raw.get("stryker-config", raw)
    return list(inner.get("test-projects", []))


TestFileResolver = Callable[[str, Sequence[str], Path], Path | None]


def default_resolve_test_file(
    source: str, test_projects: Sequence[str], repo_root: Path
) -> Path | None:
    """Best-effort convention search for a source file's test file.

    Looks under each configured test-project directory for
    ``<Stem>Tests.cs`` / ``<Stem>Test.cs`` / ``<Stem>Specs.cs``. Returns the
    first hit, or None when no conventional pairing is found (the caller skips
    that file rather than guessing — never a silent mis-target)."""
    stem = Path(source).stem
    for tp in test_projects:
        tp_dir = (Path(repo_root) / tp).parent
        if not tp_dir.exists():
            continue
        for suffix in _TEST_FILE_SUFFIXES:
            for hit in sorted(tp_dir.rglob(f"{stem}{suffix}")):
                return hit
    return None


def build_loop_command(
    *,
    config: Path,
    source_file: str,
    source_path: str,
    test_file: Path,
    report: Path,
    model: str | None,
    max_rounds: int,
) -> list[str]:
    """Build the ``mutation_kill_loop`` invocation. ``--headless`` is forced —
    the pipeline is unattended and can never depend on a live agent turn."""
    cmd = [
        PYTHON,
        LOOP_SCRIPT,
        "--headless",
        "--config",
        str(config),
        "--file",
        source_file,
        "--source-path",
        str(source_path),
        "--test-file",
        str(test_file),
        "--report",
        str(report),
        "--max-rounds",
        str(max_rounds),
    ]
    if model:
        cmd += ["--model", model]
    return cmd


def launch_survivor_fix(
    shard: str,
    *,
    repo_root: Path,
    out_dir: Path,
    config_path: Path,
    model: str | None,
    max_rounds: int,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    resolve_test_file: TestFileResolver | None = None,
    log: Callable[[str], None] = print,
) -> FixOutcome:
    """Launch the forced-headless survivor-fix loop for a shard's survivors.

    Invokes ``mutation_kill_loop`` (always with ``--headless``) once per source
    file that still has survivors, seeding round 1 from the shard's report.
    Runs from ``repo_root`` so fixes commit onto ``HEAD`` — that is what makes
    the *next* shard's worktree compounding.

    Returns a :class:`FixOutcome`. ``ok`` is True when every launched fix
    exited zero or the dedicated GenerationExhausted exit code 5 (or none
    were launched); False the moment one exits any other non-zero code. The
    implementation does not distinguish the fatal-revert exit code 4
    (``mutation_kill_headless``/``mutation_kill_loop_python`` #1598) from any
    other non-zero, non-5 code — every such exit is treated identically as a
    failed revert, which means the working tree may be in an
    unknown/possibly-mutated state, so processing stops for the remaining
    files in this shard rather than silently continuing onto a tree that may
    already be broken. Exit code 4 is ``RevertFailed`` specifically — a
    failed revert. Exit code 5 covers two distinct outcomes that both map to
    the same code: true GenerationExhausted (a fully spent
    retry-then-downgrade budget) and any other clean RuntimeError (e.g. a
    generation timeout, or a mutmut/Stryker infrastructure failure — not
    exhaustion). Both are carved out from the fatal case: this file is
    logged as unfixed and the loop continues to the next file in the shard
    (the tree was not mutated), matching ``mutation-kill.md``'s documented
    exhaustion contract that ```--all` continues``` (#1908 review) — but the
    pipeline's overall exit code becomes ``EXIT_GENERATION_EXHAUSTED`` (5) at
    the end if any file across any shard hit either outcome, unless a hard
    failure elsewhere makes it 1 (``main()``'s 3-branch priority: failed >
    exhausted/unresolved/no_report > clean).

    Two more outcomes, previously silently swallowed as a bare ``True`` (#1951):
    a survivor whose test file never resolves (``FixOutcome.unresolved``, one
    entry per such survivor — logged ``Agent SKIP: no test file resolved`` but
    the loop continues, since other survivors in the shard may still resolve)
    and a shard with no Stryker report at all (``FixOutcome.no_report``) —
    both now propagate to the run-level result instead of reading identically
    to a fully clean run with zero fix attempts made.
    """
    resolve_test_file = resolve_test_file or default_resolve_test_file
    report = report_path(out_dir)
    if not report.exists():
        log(f"[{ts()}] Agent SKIP: no report for {_safe(shard)}")
        return FixOutcome(ok=True, exhausted=[], unresolved=[], no_report=True)
    files = survivor_source_files(report)
    if not files:
        log(f"[{ts()}] Agent SKIP: no survivors in {_safe(shard)}")
        return FixOutcome(ok=True, exhausted=[], unresolved=[], no_report=False)

    exhausted: list[str] = []
    unresolved: list[str] = []
    test_projects = shard_test_projects(config_path)
    for source in files:
        test_file = resolve_test_file(source, test_projects, repo_root)
        if test_file is None:
            log(f"[{ts()}] Agent SKIP: no test file resolved for {_safe(source)}")
            unresolved.append(f"{_safe(shard)}/{_safe(source)}")
            continue
        cmd = build_loop_command(
            config=config_path,
            source_file=Path(source).name,
            source_path=source,
            test_file=test_file,
            report=report,
            model=model,
            max_rounds=max_rounds,
        )
        log(f"[{ts()}] Agent START (headless): {_safe(shard)} — {_safe(source)}")
        result = run(cmd, cwd=str(repo_root))
        rc = result.returncode
        if rc == EXIT_GENERATION_EXHAUSTED:
            log(
                f"[{ts()}] Agent UNFIXED (headless, clean): {_safe(shard)} — "
                f"{_safe(source)} (exit {rc}) — retry budget spent OR a "
                "clean generation/infrastructure failure (#1956: exit 5 "
                "covers both since #1939, so this line names the OUTCOME, "
                "not a specific cause); logging this file as unfixed and "
                "continuing to the next file in this shard (the tree was "
                "not mutated) — the pipeline's overall exit code becomes "
                "EXIT_GENERATION_EXHAUSTED (5) at the end unless a hard "
                "failure elsewhere makes it 1"
            )
            exhausted.append(f"{_safe(shard)}/{_safe(source)}")
            continue
        if rc != 0:
            log(
                f"[{ts()}] Agent FAILED (headless): {_safe(shard)} — "
                f"{_safe(source)} (exit {rc}) — stopping further files in "
                "this shard; the working tree may be left in an "
                "unknown/possibly-mutated state (this treats every "
                "non-4-non-5 exit the same as a failed revert — see #1930)"
            )
            return FixOutcome(
                ok=False, exhausted=exhausted, unresolved=unresolved, no_report=False
            )
    return FixOutcome(ok=True, exhausted=exhausted, unresolved=unresolved, no_report=False)


# ── Resume (skip-existing wins over max-age) ────────────────────────────────────


def report_age_seconds(out_dir: Path) -> float | None:
    rp = report_path(out_dir)
    if not rp.exists():
        return None
    return time.time() - rp.stat().st_mtime


def should_skip(
    out_dir: Path,
    *,
    skip_existing: bool,
    max_age_hours: float,
    shard: str,
    log: Callable[[str], None] = print,
) -> bool:
    """Resume gate. ``--skip-existing`` is evaluated **first**, so it wins over
    ``--max-age-hours``: any existing report is skipped regardless of its age.
    ``--max-age-hours`` only applies when ``--skip-existing`` is not set.
    """
    age = report_age_seconds(out_dir)
    if age is None:
        return False
    if skip_existing:
        log(f"[{ts()}] SKIPPED ({shard}): --skip-existing wins over --max-age-hours")
        return True
    if max_age_hours > 0 and age < max_age_hours * 3600:
        log(
            f"[{ts()}] SKIPPED ({shard}): report {int(age / 60)}m old "
            f"< --max-age-hours {max_age_hours}"
        )
        return True
    return False


# ── Summary (honest score) ──────────────────────────────────────────────────────


def print_summary(
    shards: Sequence[str],
    shard_out_base: Path,
    *,
    log: Callable[[str], None] = print,
    exhausted: Sequence[str] = (),
    unresolved: Sequence[str] = (),
    no_report: Sequence[str] = (),
    skipped: Sequence[str] = (),
) -> None:
    """Print the per-shard honest score with Timeout and NoCoverage broken out
    separately — never the timeout-inflated reported score (AC3).

    Four run-level outcome lines are appended when non-empty — each a case
    that previously read identically to a fully clean run (#1951):

    - ``EXHAUSTED files (N)`` — ``shard/source`` entries that hit
      ``EXIT_GENERATION_EXHAUSTED`` (5): either true GenerationExhausted (a
      fully spent retry-then-downgrade budget) or any other clean
      ``RuntimeError`` (e.g. a generation timeout, or a mutmut/Stryker
      infrastructure failure — not exhaustion); see ``launch_survivor_fix``.
    - ``UNRESOLVED test file (N)`` — ``shard/source`` entries where
      ``resolve_test_file`` never found a conventional pairing.
    - ``NO REPORT shards (N)`` — shards Stryker produced no report for.
    - ``SKIPPED shards (N)`` — shards resumed past via ``--skip-existing``/
      ``--max-age-hours``; informational only, never affects the exit code.
    """
    log("=== Pipeline summary ===")
    for shard in shards:
        rp = report_path(Path(shard_out_base) / shard)
        if not rp.exists():
            log(f"  {shard}: no report")
            continue
        s = mutation_report.score_report(rp)
        log(
            f"  {shard}: honest={s.honest_score:.1f}%  "
            f"killed={s.killed} survived={s.survived} "
            f"timeout={s.timeout} nocoverage={s.no_coverage}"
        )
    if skipped:
        log(f"\nSKIPPED shards ({len(skipped)}): " + ", ".join(skipped))
    if no_report:
        log(f"\nNO REPORT shards ({len(no_report)}): " + ", ".join(no_report))
    if unresolved:
        log(f"\nUNRESOLVED test file ({len(unresolved)}): " + ", ".join(unresolved))
    if exhausted:
        log(f"\nEXHAUSTED files ({len(exhausted)}): " + ", ".join(exhausted))


# ── Orchestration ───────────────────────────────────────────────────────────────


def process_shard(
    shard: str,
    *,
    repo_root: Path,
    worktree_base: Path,
    shard_out_base: Path,
    stryker_bin: str,
    model: str | None,
    max_rounds: int,
    skip_agent: bool,
    skip_existing: bool,
    max_age_hours: float,
    log: Callable[[str], None] = print,
    run_stryker: StrykerRunner | None = None,
    run: Callable[..., object] = subprocess.run,
    resolve_test_file: TestFileResolver | None = None,
    git_run: GitRunner | None = None,
    events: list[tuple] | None = None,
) -> ShardOutcome:
    """Process one shard end to end. Returns a :class:`ShardOutcome` whose
    ``status`` is ``"ok"`` / ``"failed"`` / ``"skipped"``, with
    ``launch_survivor_fix``'s :class:`FixOutcome` fields propagated up
    unchanged for shards that reach the survivor-fix stage. ``events`` (when
    supplied) records the worktree-creation and fix-launch ordering so tests
    can assert compounding sequencing."""
    out_dir = Path(shard_out_base) / shard
    if should_skip(
        out_dir,
        skip_existing=skip_existing,
        max_age_hours=max_age_hours,
        shard=shard,
        log=log,
    ):
        return ShardOutcome("skipped", [], [], False)

    wt = Path(worktree_base) / f"shard-{shard}"
    worktree_add(repo_root, wt, git_run=git_run)
    if events is not None:
        events.append(("worktree_add", shard))
    log(f"[{ts()}] Shard START: {shard}")
    try:
        ok = run_shard_stryker(
            shard,
            repo_root=repo_root,
            worktree=wt,
            out_dir=out_dir,
            stryker_bin=stryker_bin,
            log=log,
            run_stryker=run_stryker,
        )
    finally:
        worktree_remove(repo_root, wt, git_run=git_run)

    if not ok:
        return ShardOutcome("failed", [], [], False)
    log(f"[{ts()}] Shard DONE: {shard}")

    if not skip_agent:
        fix = launch_survivor_fix(
            shard,
            repo_root=repo_root,
            out_dir=out_dir,
            config_path=shard_config_path(repo_root, shard),
            model=model,
            max_rounds=max_rounds,
            run=run,
            resolve_test_file=resolve_test_file,
            log=log,
        )
        if events is not None:
            events.append(("fix", shard))
        status = "ok" if fix.ok else "failed"
        return ShardOutcome(status, fix.exhausted, fix.unresolved, fix.no_report)
    return ShardOutcome("ok", [], [], False)


def run_all(
    shards: Sequence[str],
    *,
    repo_root: Path,
    worktree_base: Path,
    shard_out_base: Path,
    stryker_bin: str,
    model: str | None,
    max_rounds: int,
    skip_agent: bool,
    skip_existing: bool,
    max_age_hours: float,
    log: Callable[[str], None] = print,
    run_stryker: StrykerRunner | None = None,
    run: Callable[..., object] = subprocess.run,
    resolve_test_file: TestFileResolver | None = None,
    git_run: GitRunner | None = None,
    events: list[tuple] | None = None,
) -> ShardRunResult:
    """Process every shard **sequentially** (compounding depends on ordering).
    Returns a :class:`ShardRunResult` collecting, across all shards: failed
    shards, exhausted/unresolved source files, no-report shards, and
    skipped shards (#1951)."""
    failed: list[str] = []
    exhausted: list[str] = []
    unresolved: list[str] = []
    no_report: list[str] = []
    skipped: list[str] = []
    for shard in shards:
        outcome = process_shard(
            shard,
            repo_root=repo_root,
            worktree_base=worktree_base,
            shard_out_base=shard_out_base,
            stryker_bin=stryker_bin,
            model=model,
            max_rounds=max_rounds,
            skip_agent=skip_agent,
            skip_existing=skip_existing,
            max_age_hours=max_age_hours,
            log=log,
            run_stryker=run_stryker,
            run=run,
            resolve_test_file=resolve_test_file,
            git_run=git_run,
            events=events,
        )
        if outcome.status == "failed":
            failed.append(shard)
        elif outcome.status == "skipped":
            skipped.append(shard)
        exhausted.extend(outcome.exhausted)
        unresolved.extend(outcome.unresolved)
        if outcome.no_report:
            no_report.append(shard)
    return ShardRunResult(failed, exhausted, unresolved, no_report, skipped)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stryker_shard_pipeline.py",
        description="Sharded Stryker pipeline with compounding worktrees and timeout-abort",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "shards", nargs="*", default=[], help="Shards to run (default: all discovered)"
    )
    parser.add_argument("--repo-root", help="Repo root (default: cwd)")
    parser.add_argument("--stryker-bin", default="dotnet-stryker", help="Stryker executable")
    parser.add_argument(
        "--model",
        help="Generation model for the forced-headless survivor-fix loop.",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=3, help="Survivor-fix rounds per file (default: 3)"
    )
    parser.add_argument(
        "--skip-agent", action="store_true", help="Run shards only; skip survivor-fix"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip shards with an existing report, any age (wins over --max-age-hours)",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=0,
        help="Skip shards whose report is younger than N hours (ignored under --skip-existing)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Exit code follows a 3-branch priority, failure first:

    - ``1`` — one or more shards failed (``run_all``'s ``failed`` list is
      non-empty). Takes priority over exhaustion. A shard is marked failed
      when ``launch_survivor_fix`` returns a :class:`FixOutcome` with
      ``ok=False`` — which happens on any non-zero, non-5 per-file exit code
      (most commonly ``EXIT_REVERT_FAILED``, ``4``); this branch is where
      that per-file signal ends up, since ``main()`` never returns ``4``
      itself.
    - ``EXIT_GENERATION_EXHAUSTED`` (``5``) — no shard failed, but at least
      one of three "a survivor was not addressed this run" outcomes fired
      (#1951): ``exhausted`` is non-empty (a true ``GenerationExhausted`` — a
      fully spent retry-then-downgrade budget — or any other clean
      ``RuntimeError`` such as a generation timeout), ``unresolved`` is
      non-empty (a survivor whose test file never resolved), or
      ``no_report`` is non-empty (a shard Stryker produced no report for).
      All three previously read identically to a fully clean run; only
      ``exhausted`` got run-level visibility before this fix.
    - ``0`` — fully clean: no failures, no exhaustions, no unresolved test
      files, no missing reports. (``skipped`` shards — resumed past via
      ``--skip-existing``/``--max-age-hours`` — are reported in the summary
      but never affect the exit code; see ``print_summary``.)
    """
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()

    try:
        all_shards = discover_shards(repo_root)
    except ShardSetupMissing as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    shards = list(args.shards) if args.shards else all_shards

    worktree_base = repo_root / ".stryker-worktrees"
    shard_out_base = repo_root / "StrykerOutput" / "shards"
    worktree_base.mkdir(parents=True, exist_ok=True)
    shard_out_base.mkdir(parents=True, exist_ok=True)

    # DOTNET_ROOT resolution is delegated to the wrapper (AC4) and exported so
    # every shard's Stryker subprocess inherits it.
    dotnet_root, err = wrapper.resolve_dotnet_root(
        preset=os.environ.get("DOTNET_ROOT"),
        candidates=wrapper.default_probe_candidates(),
    )
    if err is not None:
        sys.stderr.write(err)
        return wrapper.EXIT_NO_DOTNET_SDK
    assert dotnet_root is not None
    os.environ["DOTNET_ROOT"] = dotnet_root

    print(f"Pipeline: {' '.join(shards)}")
    result = run_all(
        shards,
        repo_root=repo_root,
        worktree_base=worktree_base,
        shard_out_base=shard_out_base,
        stryker_bin=args.stryker_bin,
        model=args.model,
        max_rounds=args.max_rounds,
        skip_agent=args.skip_agent,
        skip_existing=args.skip_existing,
        max_age_hours=args.max_age_hours,
    )

    print_summary(
        shards,
        shard_out_base,
        exhausted=result.exhausted,
        unresolved=result.unresolved,
        no_report=result.no_report,
        skipped=result.skipped,
    )
    if result.failed:
        print(f"\nFAILED shards: {' '.join(result.failed)}")
        return 1
    if result.exhausted or result.unresolved or result.no_report:
        return EXIT_GENERATION_EXHAUSTED
    return 0


if __name__ == "__main__":
    sys.exit(main())
