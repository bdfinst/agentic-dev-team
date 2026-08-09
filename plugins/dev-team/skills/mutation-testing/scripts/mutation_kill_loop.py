#!/usr/bin/env python3
"""mutation_kill_loop.py — config-driven, deterministic survivor-kill loop.

Migrated from the ACI ``nextgen-test-upgrade-process`` mutation agent and
de-hardcoded: nothing repo-specific lives here. Project / test-project /
mutate targets come from ``stryker-config.json``; ``DOTNET_ROOT`` resolution
and ``.sln`` hide/restore reuse the shipped ``csharp_stryker_net_wrapper``;
scoring and survivor extraction reuse ``mutation_report``.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). The only
non-stdlib imports are the sibling plugin modules in this same ``scripts/``
directory.

**Scope (#1562).** This module owns config parsing, the scoped Stryker run,
verify/commit/revert, and ``run_for_file`` orchestration. Insertion mechanics
(detect-or-refuse C# source manipulation) live in ``mutation_kill_insert.py``,
a stdlib-only leaf this module imports from — never the reverse — mirroring
the wrapper/report split already established by
``csharp_stryker_net_wrapper.py`` / ``mutation_report.py``. Headless
generation and the ``--headless`` CLI live in ``mutation_kill_headless.py``,
which is a different shape: a thin CLI layer built atop this module's public
API, so it imports back from here at module scope. This module only reaches
into it lazily, inside ``if __name__ == "__main__":``, specifically to avoid
the circular import that a module-scope import in both directions would
create.

**Shared mechanics (#1583).** ``_timeout_from_env``, ``git_revert``,
``git_reset_and_revert``, ``git_commit``, and the "no improvement across
rounds" stop predicate are imported from ``mutation_kill_shared.py`` rather
than defined here — they were byte-for-byte duplicated with
``mutation_kill_loop_python.py`` (the Python/mutmut sibling) before that
module existed. See its module docstring for the full rationale.

**Generation is a seam, not a mechanism.** The loop never decides *what*
tests to write — a caller supplies a ``generate`` callable that returns the
new test-method text. The default (interactive) path is agent-driven: the
``mutation-kill`` agent calls :func:`run_for_file` directly, passing a
``generate`` hook backed by a live agent turn. A ``--headless`` CLI mode
(``mutation_kill_headless.py``) shells to ``claude --print`` for unattended
(CI / shard-pipeline) runs. Invoking the CLI with neither an injected
generator nor ``--headless`` fails fast at startup — before any Stryker run
or file mutation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# The `Generator` alias below is a real runtime expression
# (mutation_kill_headless imports the name), so `from __future__ import
# annotations` cannot defer it — it must be subscriptable at import time.
# collections.abc generics have been since 3.9, which the 3.10 floor
# (ADR 0031) clears.
from typing import NamedTuple

import csharp_stryker_net_wrapper as wrapper
import mutation_kill_shared
import mutation_report
import mutation_safety_gate
from mutation_kill_insert import apply_generated_methods, count_methods
from mutation_kill_shared import (
    GIT_TIMEOUT_S,  # noqa: F401 — re-exported for tests (loop.GIT_TIMEOUT_S)
    _timeout_from_env,
    git_commit,
    git_reset_and_revert,
    git_revert,
    stop_reason,
)

# A generator is any callable the agent (or the headless CLI) supplies: given
# the source filename, the surviving mutants, the source text, and the
# current test text, it returns the raw text of new test methods to insert.
# The loop owns everything *around* this call; the callable owns the single
# genuinely-LLM step.
Generator = Callable[[str, list[dict], str, str], str]


class _Timeout(NamedTuple):
    """A timeout value paired with the env var that overrides it — kept
    together so the two can't drift out of sync at a ``_run_with_timeout``
    call site (#1593 review)."""

    seconds: float
    env_var_name: str


def _make_timeout(env_var_name: str, default: int) -> _Timeout:
    """Parse+pair in one step, so the env-var name is written once, not
    once for ``_timeout_from_env`` and again for the ``_Timeout`` it feeds."""
    return _Timeout(_timeout_from_env(env_var_name, default), env_var_name)


# Timeouts for the long-running subprocesses this loop shells out to. Each is
# overridable via env var since a legitimately slow project (a large solution,
# a heavyweight test suite) may need a larger budget than these defaults —
# unlike the 30s used by this codebase's git-shelling helpers, these
# subprocesses (a Stryker run, a dotnet build/test) routinely run for minutes.
_STRYKER_TIMEOUT = _make_timeout("DEV_TEAM_MUTATION_STRYKER_TIMEOUT_S", 3600)
_BUILD_TIMEOUT = _make_timeout("DEV_TEAM_MUTATION_BUILD_TIMEOUT_S", 600)
_TEST_TIMEOUT = _make_timeout("DEV_TEAM_MUTATION_TEST_TIMEOUT_S", 600)
# GIT_TIMEOUT_S itself comes from mutation_kill_shared (imported above) —
# shared verbatim with mutation_kill_loop_python.py (#1583). No local
# _GIT_TIMEOUT _Timeout pairing exists here anymore: git_revert/git_commit/
# git_reset_and_revert are themselves imported from that module, so they
# already close over its own GIT_TIMEOUT_S rather than taking one as a param.

STRYKER_RUN_TIMEOUT_S = _STRYKER_TIMEOUT.seconds
DOTNET_BUILD_TIMEOUT_S = _BUILD_TIMEOUT.seconds
DOTNET_TEST_TIMEOUT_S = _TEST_TIMEOUT.seconds


def _run_with_timeout(
    argv: list[str],
    timeout_spec: _Timeout,
    *,
    operation_label: str,
    cwd: Path | None = None,
    capture_output: bool = False,
    text: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess | None:
    """Run ``argv`` with a bounded timeout. On ``TimeoutExpired``, logs to
    stderr and returns ``None`` instead of raising, so ``dotnet_build`` and
    ``dotnet_test`` share one timeout/log shape instead of two copies (#1593).
    ``git_revert``/``git_commit``/``git_reset_and_revert`` moved to
    ``mutation_kill_shared.py`` (#1583) with their own, behaviorally-identical
    inline timeout handling — they no longer call this helper. No
    ``shell``/``**kwargs`` passthrough: every ``argv`` runs as a list, never
    through a shell.
    ``env`` defaults to ``None`` (inherit the ambient process environment,
    today's behavior) — tests pass a scrubbed env to keep real-git regression
    tests hermetic (#1598/#1584 review, item 4 follow-up)."""
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            timeout=timeout_spec.seconds,
            capture_output=capture_output,
            text=text,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"error: {operation_label} timed out after {timeout_spec.seconds}s "
            f"(set {timeout_spec.env_var_name} to raise it)\n"
        )
        return None


# =============================================================================
# Config — everything path-shaped comes from stryker-config.json.
# =============================================================================
@dataclass(frozen=True)
class LoopConfig:
    """The subset of a ``stryker-config.json`` the loop needs.

    ``project`` is the mutated project (optional — Stryker infers it from the
    solution when omitted). ``test_projects`` drives every ``dotnet build`` and
    ``dotnet test`` target — never a hardcoded path. ``solution`` is the main
    ``.sln`` hidden during a scoped run.
    """

    project: str | None
    test_projects: list[str]
    mutate: list[str]
    solution: str | None


def load_loop_config(config_path: Path) -> LoopConfig:
    """Parse ``stryker-config.json``, tolerating the wrapper shape.

    Stryker configs may nest everything under a top-level ``"stryker-config"``
    key (the shape the ACI configs use) or place the keys at the top level.
    Both are accepted.
    """
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    inner = raw.get("stryker-config", raw)
    return LoopConfig(
        project=inner.get("project"),
        test_projects=list(inner.get("test-projects", [])),
        mutate=list(inner.get("mutate", [])),
        solution=inner.get("solution"),
    )


def dotnet_test_project_targets(config: LoopConfig) -> list[str]:
    """Both the build and test targets are exactly the configured test-projects."""
    return list(config.test_projects)


# =============================================================================
# Scoped Stryker run — goes THROUGH the wrapper (AC4).
# =============================================================================
def make_scoped_config(config: LoopConfig, source_file: str) -> dict:
    """Build a Stryker config scoped to a single source file.

    Carries the configured solution / project / test-projects forward and
    narrows ``mutate`` to just the target file with per-test coverage for fast
    feedback. Keys whose configured value is ``None`` are dropped so Stryker
    infers them.
    """
    scoped = {
        "solution": config.solution,
        "project": config.project,
        "test-projects": config.test_projects,
        "mutate": [f"**/{source_file}"],
        "coverage-analysis": "perTest",
        "reporters": ["json"],
    }
    scoped = {k: v for k, v in scoped.items() if v is not None}
    return {"stryker-config": scoped}


def _write_scoped_config(config: LoopConfig, source_file: str) -> Path:
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", prefix="stryker-scoped-"
    ) as tmp:
        json.dump(make_scoped_config(config, source_file), tmp)
        path = Path(tmp.name)
    return path


def _validate_solution_path(solution: str, *, cwd: Path | None = None) -> Path:
    """Reject a ``stryker-config.json`` ``solution`` value that would escape
    the working tree once used to derive ``sln_hidden``, and return the
    resolved, validated absolute path.

    ``solution`` is read verbatim from ``stryker-config.json`` and, before
    this check existed, was concatenated straight into a filename
    (``f"{config.solution}.stryker-hidden"``) with no validation — a
    traversal-shaped value (e.g. ``"../../etc/cron.d/evil"``) would let a
    hostile config target a file outside the repo if the config is ever read
    from an untrusted checkout (#1598). Resolves ``solution`` against
    ``cwd`` (or the current working directory) and rejects it unless the
    resolved path stays under that root.

    Callers must build ``sln``/``sln_hidden`` from THIS function's return
    value, not by independently re-deriving ``Path(config.solution)`` — the
    latter resolves against the *process* working directory when
    ``wrapper.hide_sln``/``restore_sln``'s bare ``Path.rename()`` runs, not
    against ``cwd`` (which only ever reaches ``subprocess.run``), so the
    validated path and the actually-renamed path could silently diverge
    whenever a caller passes a ``cwd`` different from the real process cwd
    (caught in #1598/#1584 review).

    **Requires a relative ``solution``; an absolute value is rejected in
    every practical case (#1598/#1584 review, item 11).** ``pathlib``'s ``/``
    operator silently discards ``base`` outright when the right-hand operand
    is itself absolute (``base / "/etc/passwd" == Path("/etc/passwd")``), so
    ``candidate`` becomes that absolute value verbatim — not "``base`` plus
    the absolute path" as the name might suggest. The ``relative_to(base)``
    check below then rejects it as escaping, UNLESS the absolute value
    happens to already lie under ``base`` (a degenerate case with no
    practical use, since a relative value achieves the same result without
    depending on ``base``'s exact prefix). This narrows what a bare
    ``Path(config.solution)`` used to accept before this validation existed
    — an absolute ``solution`` is not a supported input; pass a
    repo-relative path.
    """
    base = (cwd or Path.cwd()).resolve()
    candidate = (base / solution).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError(
            f"stryker-config.json 'solution' escapes the working tree: {solution!r}"
        ) from None
    return candidate


def run_scoped_stryker(
    config: LoopConfig,
    source_file: str,
    *,
    output_dir: Path,
    stryker_bin: str = "dotnet-stryker",
    cwd: Path | None = None,
) -> Path:
    """Run Stryker scoped to one file; return the report path.

    DOTNET_ROOT resolution and ``.sln`` hide/restore are delegated to
    ``csharp_stryker_net_wrapper`` — this function never re-implements either
    (AC4). The ``.sln`` is hidden for the duration of the run and restored on
    every exit path via ``finally``.
    """
    dotnet_root, err = wrapper.resolve_dotnet_root(
        preset=os.environ.get("DOTNET_ROOT"),
        candidates=wrapper.default_probe_candidates(),
    )
    if err is not None:
        raise RuntimeError(err)
    assert dotnet_root is not None
    env = {**os.environ, "DOTNET_ROOT": dotnet_root}

    sln: Path | None = None
    if config.solution:
        # Use the validated, resolved path for BOTH the check and the actual
        # rename below — never re-derive a second, independently-resolved
        # Path(config.solution) (#1598/#1584 review: the two could diverge).
        sln = _validate_solution_path(config.solution, cwd=cwd)

    config_path = _write_scoped_config(config, source_file)
    # Fixed name, no PID suffix. A PID-suffixed name was tried (#1584) to
    # guard two processes scoped-running Stryker against the same solution
    # concurrently, but reverted after review: stryker_shard_pipeline.py
    # runs shards sequentially, not concurrently (see its own module
    # docstring), so that race doesn't exist today — and a PID-suffixed name
    # is invisible to csharp_stryker_net_wrapper.py's check_stale_hidden_sln()
    # crash-recovery, which looks for the exact literal ".stryker-hidden"
    # suffix, so a crashed run would leave an orphaned hidden .sln that
    # existing recovery can no longer find or restore. If true concurrent
    # execution is ever introduced, add uniqueness at the
    # csharp_stryker_net_wrapper level (shared with
    # csharp_stryker_net_slice_runner.py) with a matching update to
    # check_stale_hidden_sln's stale-file scan.
    sln_hidden = Path(f"{sln}.stryker-hidden") if sln is not None else None
    if sln is not None and sln_hidden is not None:
        # Crash-recovery refusal (#1598/#1584 review, item 6): the wrapper's
        # own main() and csharp_stryker_net_slice_runner.py both call this
        # before hide_sln — a stale hidden .sln left over from a prior crash
        # is exactly what the fixed (no-PID) hidden-filename choice above is
        # meant to make findable by this check. This caller never wired it
        # in, silently skipping the recovery it depends on.
        stale_err = wrapper.check_stale_hidden_sln(sln, sln_hidden)
        if stale_err is not None:
            config_path.unlink(missing_ok=True)
            raise RuntimeError(stale_err)
    try:
        if sln is not None and sln_hidden is not None:
            wrapper.hide_sln(sln, sln_hidden)
        try:
            # Deliberately not routed through _run_with_timeout: a Stryker
            # timeout aborts the whole file (raise), it doesn't return a
            # None-means-failure signal for a caller to revert-and-continue
            # like dotnet_build/dotnet_test/git_revert/git_commit do.
            subprocess.run(
                [
                    stryker_bin,
                    "--config-file",
                    str(config_path),
                    "--output",
                    str(output_dir),
                ],
                env=env,
                cwd=cwd,
                check=False,
                timeout=_STRYKER_TIMEOUT.seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"error: Stryker run timed out after {_STRYKER_TIMEOUT.seconds}s for "
                f"{source_file} (set {_STRYKER_TIMEOUT.env_var_name} to raise it)"
            ) from exc
    finally:
        if sln is not None and sln_hidden is not None:
            wrapper.restore_sln(sln, sln_hidden)
        config_path.unlink(missing_ok=True)

    return Path(output_dir) / "reports" / "mutation-report.json"


def extract_survivors(report_path: Path, source_file: str) -> list[dict]:
    """Return the surviving mutants for one source file (flattened).

    Delegates grouping/extraction to :func:`mutation_report.survivors_by_mutator`.
    """
    grouped = mutation_report.survivors_by_mutator(report_path, source_file)
    return [mutant for mutants in grouped.values() for mutant in mutants]


# =============================================================================
# Verify — dotnet build/test go through subprocess here; git_revert/
# git_reset_and_revert/git_commit are imported from mutation_kill_shared.py
# (#1583) rather than defined in this section.
# =============================================================================
def dotnet_build(targets: Sequence[str], *, cwd: Path | None = None) -> bool:
    """Build every configured test-project. False if any target fails or
    times out."""
    for target in targets:
        result = _run_with_timeout(
            ["dotnet", "build", target, "-c", "Debug", "--nologo"],
            _BUILD_TIMEOUT,
            operation_label=f"dotnet build for {target}",
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result is None or result.returncode != 0:
            return False
    return True


# Capital-F "Failed:" only — a per-assembly `dotnet test` summary line, NOT
# the newer SDK's trailing lowercase rollup ("Test summary: ... failed: 0 ...").
# Kept case-sensitive (no re.IGNORECASE) deliberately: matching the rollup
# line too would double-count every assembly's failures on top of the
# rollup's own total (#1598/#1584 review, item 12 — see
# test_sum_failed_counts_is_case_sensitive_not_double_counting_the_rollup_line
# for a fixture that actually distinguishes the two, unlike a fixture where
# both a correct and a buggy (case-insensitive) scan sum to 0).
_FAILED_COUNT_RE = re.compile(r"Failed:\s*(\d+)")


def _sum_failed_counts(text: str) -> int:
    """Sum every capital-F "Failed: N" occurrence in ``text``.

    Accumulates, not overwrites: a multi-assembly `dotnet test` run prints
    one "Failed: N" line per assembly, and a last-match-wins scan would let
    an early assembly's failures be silently masked by a later, clean
    assembly's "Failed: 0" line (#1598).
    """
    return sum(int(m.group(1)) for m in _FAILED_COUNT_RE.finditer(text))


def dotnet_test(
    targets: Sequence[str], test_filter: str, *, cwd: Path | None = None
) -> bool:
    """Run the scoped test filter across every test-project. False on any
    non-zero exit, reported failure, or timeout."""
    for target in targets:
        result = _run_with_timeout(
            [
                "dotnet",
                "test",
                target,
                "-c",
                "Debug",
                "--no-build",
                "--filter",
                f"FullyQualifiedName~{test_filter}",
            ],
            _TEST_TIMEOUT,
            operation_label=f"dotnet test for {target}",
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result is None:
            return False
        if result.returncode != 0 or _sum_failed_counts(result.stdout + result.stderr) > 0:
            return False
    return True


def _commit_message(
    round_num: int,
    source_file: str,
    survivors: int,
    new_methods: str,
    *,
    generator_label: str | None = None,
    label_override: str | None = None,
) -> str:
    count = count_methods(new_methods)
    # Whitespace-collapsed the same way append_generator_trailer sanitizes
    # generator_label (#1607): source_file is caller-supplied, and a value
    # containing a newline could otherwise forge an extra "Generator:"
    # trailer line into the commit message.
    safe_source_file = " ".join(str(source_file).split())
    message = (
        f"test(mutation): kill round {round_num} — {safe_source_file}\n\n"
        f"{count} new test method(s) targeting {survivors} surviving mutant(s)"
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
    (``main()`` here and the ``_loop_fixture`` test helper), separating "how
    to run this file" from ``run_for_file``'s own ``generate``/``max_rounds``
    controls (#1561). ``generator_label``, when set, is recorded in the
    commit message as an audit trail (e.g. distinguishing an unattended
    ``--headless`` commit from an agent-driven one).

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

    config: LoopConfig
    test_file: Path
    source_path: Path
    output_dir: Path
    stryker_bin: str = "dotnet-stryker"
    cwd: Path | None = None
    log: Callable[[str], None] = print
    initial_report_path: Path | None = None
    generator_label: str | None = None
    label_override_provider: Callable[[], str | None] | None = None


def _score_round(
    round_num: int,
    source_file: str,
    ctx: RunContext,
    *,
    prev_survivor_count: int | None,
) -> tuple[list[dict], int] | None:
    """Score one round: baseline-seed-or-scoped-run → survivor extraction →
    log → stop-checks.

    Returns ``(survivors, survivor_count)`` to continue the round, or
    ``None`` when the file is done — no survivors, or no improvement over
    the previous round.
    """
    if ctx.initial_report_path is not None and round_num == 1:
        report_path = Path(ctx.initial_report_path)
    else:
        report_path = run_scoped_stryker(
            ctx.config,
            source_file,
            output_dir=ctx.output_dir,
            stryker_bin=ctx.stryker_bin,
            cwd=ctx.cwd,
        )

    survivors = extract_survivors(report_path, source_file)
    survivor_count = len(survivors)
    # File-scoped, not score_report(): a baseline-seeded round 1 report can
    # cover multiple files (#1545) — score_report() would leak another
    # file's score into this line.
    summary = mutation_report.score_report_for_file(report_path, source_file)
    ctx.log(
        f"  round {round_num}: honest={summary.honest_score:.1f}% "
        f"survivors={survivor_count}"
    )

    # Mirrors the Python loop's equivalent guard (#1359/#1606): mutation_report's
    # own documented contract is to return a fully-zeroed ScoreSummary (never
    # raise) for an absent/empty report or an unmatched file key, and
    # run_scoped_stryker runs Stryker with check=False — a crashed Stryker
    # process, or a scoped-config file-key mismatch, can therefore yield
    # survivor_count == 0 here with zero mutants ever actually having run.
    # Without this check that would be indistinguishable from a genuine
    # "no survivors — done" convergence.
    total_mutants = summary.killed + summary.survived + summary.timeout + summary.no_coverage
    if total_mutants == 0:
        ctx.log(
            "  zero mutants generated — this is NOT convergence. Stryker "
            "produced no results at all for this file (a crashed run, or a "
            "scoped-config file-key mismatch). Stopping without declaring "
            "survivors == 0 (#1606)."
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
    """
    revert_ok = (
        git_reset_and_revert(ctx.test_file, cwd=ctx.cwd)
        if after_commit
        else git_revert(ctx.test_file, cwd=ctx.cwd)
    )
    if not revert_ok:
        raise mutation_kill_shared.RevertFailed(
            f"revert failed for {ctx.test_file} after {reason} — the "
            "working tree is left in an unknown state (mutated test "
            "content may still be on disk, uncommitted)"
        )


def _verify_and_commit(
    round_num: int,
    source_file: str,
    survivor_count: int,
    new_methods: str,
    ctx: RunContext,
) -> int | None:
    """Build → scoped test → commit-on-green / revert-on-failure.

    Returns ``survivor_count`` on a successful commit, or ``None`` when the
    round is abandoned (build failure, test failure, or commit failure —
    each reverted via :func:`_revert_or_raise`, which raises if the revert
    itself fails).
    """
    if not dotnet_build(dotnet_test_project_targets(ctx.config), cwd=ctx.cwd):
        ctx.log("  build failed — reverting")
        _revert_or_raise(ctx, "a failed build")
        return None
    if not dotnet_test(dotnet_test_project_targets(ctx.config), ctx.test_file.stem, cwd=ctx.cwd):
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
            new_methods,
            generator_label=ctx.generator_label,
            label_override=label_override,
        ),
        ctx.test_file,
        cwd=ctx.cwd,
    )
    if not committed:
        # A failed/timed-out commit is a round failure, not a silent
        # success — without this check the loop would advance to the next
        # round believing this one landed, while the test methods sit
        # uncommitted (and possibly still staged) on disk (#1598).
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

    # Read once and thread the text through both the generation prompt and
    # the insertion helper below — apply_generated_methods (and, inside it,
    # insert_before_class_close) accept the already-read text instead of
    # re-reading test_file from disk a second and third time (#1584).
    test_text = ctx.test_file.read_text(encoding="utf-8")
    new_methods = generate(
        source_file,
        survivors,
        ctx.source_path.read_text(encoding="utf-8"),
        test_text,
    )

    # No test_text= here on purpose (#1598/#1584 review, item 7):
    # apply_generated_methods always does its own fresh read now, shared
    # between its duplicate-name check and the write — this pre-generation
    # `test_text` snapshot (read above, before the possibly multi-minute
    # `generate()` call) is only for the generation prompt.
    outcome = apply_generated_methods(ctx.test_file, new_methods)
    if not outcome.inserted:
        ctx.log(f"  not inserted ({outcome.reason}) — stopping")
        return None

    return _verify_and_commit(round_num, source_file, survivor_count, new_methods, ctx)


def run_for_file(
    source_file: str,
    ctx: RunContext,
    *,
    generate: Generator,
    max_rounds: int = 5,
) -> None:
    """Drive the deterministic survivor-kill loop for one source file.

    ``generate`` is the sole non-deterministic step: given survivors + context
    it returns the raw new-method text. Everything else — scoped run, scoring,
    duplicate/insert guards, build/test verification, revert-on-failure,
    commit-on-green, and the no-improvement stop — is mechanical, driven one
    round at a time by :func:`_run_round`.

    A failed revert (after a build failure, a test failure, or a failed
    commit) is fatal: it raises :class:`mutation_kill_shared.RevertFailed`
    rather than returning silently, because a revert that can't be verified
    as having succeeded means the working tree is left in an unknown,
    possibly-mutated state —
    silently continuing to the next round or file would risk committing
    mutated content later under a false assumption of a clean tree (#1598).
    A failed commit itself is also a round failure, not a silent success: it
    is reverted (unstage + restore, via :func:`git_reset_and_revert`) and the
    round stops without advancing.
    """
    prev_survivor_count: int | None = None
    for round_num in range(1, max_rounds + 1):
        prev_survivor_count = _run_round(
            round_num, source_file, ctx, generate, prev_survivor_count=prev_survivor_count
        )
        if prev_survivor_count is None:
            return


if __name__ == "__main__":
    # Register this already-executing module under its real import name
    # before mutation_kill_headless's `from mutation_kill_loop import ...`
    # runs — otherwise Python can't find "mutation_kill_loop" in sys.modules
    # (this process is running as "__main__") and re-executes this file from
    # disk as a second, distinct module object (two RunContext/LoopConfig
    # class identities). Aliasing first makes the import a cache hit.
    sys.modules.setdefault("mutation_kill_loop", sys.modules[__name__])
    import mutation_kill_headless

    sys.exit(mutation_kill_headless.main())
