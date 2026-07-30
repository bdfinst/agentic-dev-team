#!/usr/bin/env python3
"""mutation_kill_loop.py — config-driven, deterministic survivor-kill loop.

Migrated from the ACI ``nextgen-test-upgrade-process`` mutation agent and
de-hardcoded: nothing repo-specific lives here. Project / test-project /
mutate targets come from ``stryker-config.json``; ``DOTNET_ROOT`` resolution
and ``.sln`` hide/restore reuse the shipped ``csharp_stryker_net_wrapper``;
scoring and survivor extraction reuse ``mutation_report``. Insertion mechanics
live in the sibling ``mutation_kill_insert``; headless generation and the CLI
entry point live in the sibling ``mutation_kill_headless`` (#1562) — this
module owns only config, the scoped Stryker run, verify/commit, and the
per-file round orchestration.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). The only
non-stdlib imports are the sibling plugin modules in this same ``scripts/``
directory.

**Generation is a seam, not a mechanism.** The loop never decides *what*
tests to write — a caller supplies a ``generate`` callable that returns the
new test-method text. The default (interactive) path is agent-driven: the
``mutation-kill`` agent calls :func:`run_for_file` directly, passing a
``generate`` hook backed by a live agent turn. ``mutation_kill_headless.py``
shells to ``claude --print`` for unattended (CI / shard-pipeline) runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import csharp_stryker_net_wrapper as wrapper
import mutation_kill_insert as insert
import mutation_report

# A generator is any callable the agent (or the headless CLI) supplies: given
# the source filename, the surviving mutants, the source text, and the
# current test text, it returns the raw text of new test methods to insert.
# The loop owns everything *around* this call; the callable owns the single
# genuinely-LLM step.
Generator = Callable[[str, list[dict], str, str], str]


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


def dotnet_build_targets(config: LoopConfig) -> list[str]:
    """Build targets are exactly the configured test-projects."""
    return list(config.test_projects)


def dotnet_test_targets(config: LoopConfig) -> list[str]:
    """Test targets are exactly the configured test-projects."""
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

    config_path = _write_scoped_config(config, source_file)
    sln = Path(config.solution) if config.solution else None
    sln_hidden = Path(f"{config.solution}.stryker-hidden") if config.solution else None
    try:
        if sln is not None and sln_hidden is not None:
            wrapper.hide_sln(sln, sln_hidden)
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
        )
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
# Verify / commit / revert — all dotnet & git go through subprocess.
# =============================================================================
def dotnet_build(targets: Sequence[str], *, cwd: Path | None = None) -> bool:
    """Build every configured test-project. False if any target fails."""
    for target in targets:
        rc = subprocess.run(
            ["dotnet", "build", target, "-c", "Debug", "--nologo"],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        ).returncode
        if rc != 0:
            return False
    return True


def dotnet_test(
    targets: Sequence[str], test_filter: str, *, cwd: Path | None = None
) -> bool:
    """Run the scoped test filter across every test-project. False on any
    non-zero exit or reported failure."""
    for target in targets:
        result = subprocess.run(
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
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        failed = 0
        for line in (result.stdout + result.stderr).splitlines():
            match = re.search(r"Failed:\s*(\d+)", line)
            if match:
                failed = int(match.group(1))
        if result.returncode != 0 or failed > 0:
            return False
    return True


def git_revert(test_file: Path, *, cwd: Path | None = None) -> None:
    """Discard working-tree changes to one file (``git checkout -- <file>``)."""
    subprocess.run(["git", "checkout", "--", str(test_file)], cwd=cwd, check=False)


def git_commit(message: str, test_file: Path, *, cwd: Path | None = None) -> bool:
    """Stage and commit only ``test_file``. Returns True on a successful commit."""
    subprocess.run(["git", "add", str(test_file)], cwd=cwd, check=False)
    rc = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    ).returncode
    return rc == 0


def _commit_message(
    round_num: int, source_file: str, survivor_count: int, method_count: int
) -> str:
    return (
        f"test(mutation): kill round {round_num} — {source_file}\n\n"
        f"{method_count} new test method(s) targeting {survivor_count} surviving mutant(s)"
    )


# =============================================================================
# Per-file loop — run → score → check → generate → insert → verify → commit.
# =============================================================================
@dataclass(frozen=True)
class RunContext:
    """Everything a round of :func:`run_for_file` needs that stays constant
    across every round for one source file — extracted (#1561) so
    ``_run_round`` takes one bundle instead of a long, mixed parameter list."""

    source_file: str
    config: LoopConfig
    test_file: Path
    source_path: Path
    output_dir: Path
    generate: Generator
    initial_report_path: Path | None = None
    stryker_bin: str = "dotnet-stryker"
    cwd: Path | None = None
    log: Callable[[str], None] = print


@dataclass(frozen=True)
class _RoundResult:
    """Outcome of one round: whether the loop should stop, and the survivor
    count to compare against next round's no-improvement check."""

    stop: bool
    survivor_count: int


def _run_round(round_num: int, prev_survivor_count: int | None, ctx: RunContext) -> _RoundResult:
    """Run one round of the survivor-kill loop for one source file.

    Mechanical scoped run → score → stop-condition checks → generate → insert
    → verify → commit-on-green/revert-on-failure. The sole non-deterministic
    step is ``ctx.generate``; everything else here is deterministic and
    mirrors :func:`run_for_file`'s pre-#1561 inline body exactly.
    """
    if ctx.initial_report_path is not None and round_num == 1:
        report_path = Path(ctx.initial_report_path)
    else:
        report_path = run_scoped_stryker(
            ctx.config,
            ctx.source_file,
            output_dir=ctx.output_dir,
            stryker_bin=ctx.stryker_bin,
            cwd=ctx.cwd,
        )

    survivors = extract_survivors(report_path, ctx.source_file)
    survivor_count = len(survivors)
    # File-scoped, not score_report(): a baseline-seeded round 1 report can
    # cover multiple files (#1545) — score_report() would leak another
    # file's score into this line.
    summary = mutation_report.score_report_for_file(report_path, ctx.source_file)
    ctx.log(
        f"  round {round_num}: honest={summary.honest_score:.1f}% "
        f"survivors={survivor_count}"
    )

    if survivor_count == 0:
        ctx.log("  no survivors — done")
        return _RoundResult(stop=True, survivor_count=survivor_count)
    if prev_survivor_count is not None and survivor_count >= prev_survivor_count:
        ctx.log("  no improvement this round — stopping")
        return _RoundResult(stop=True, survivor_count=survivor_count)

    new_methods = ctx.generate(
        ctx.source_file,
        survivors,
        ctx.source_path.read_text(encoding="utf-8"),
        ctx.test_file.read_text(encoding="utf-8"),
    )

    outcome = insert.apply_generated_methods(ctx.test_file, new_methods)
    if not outcome.inserted:
        ctx.log(f"  not inserted ({outcome.reason}) — stopping")
        return _RoundResult(stop=True, survivor_count=survivor_count)

    if not dotnet_build(dotnet_build_targets(ctx.config), cwd=ctx.cwd):
        ctx.log("  build failed — reverting")
        git_revert(ctx.test_file, cwd=ctx.cwd)
        return _RoundResult(stop=True, survivor_count=survivor_count)
    if not dotnet_test(dotnet_test_targets(ctx.config), ctx.test_file.stem, cwd=ctx.cwd):
        ctx.log("  tests failed — reverting")
        git_revert(ctx.test_file, cwd=ctx.cwd)
        return _RoundResult(stop=True, survivor_count=survivor_count)

    ctx.log("  green — committing")
    git_commit(
        _commit_message(round_num, ctx.source_file, survivor_count, outcome.method_count),
        ctx.test_file,
        cwd=ctx.cwd,
    )
    return _RoundResult(stop=False, survivor_count=survivor_count)


def run_for_file(
    source_file: str,
    *,
    config: LoopConfig,
    test_file: Path,
    source_path: Path,
    output_dir: Path,
    generate: Generator,
    max_rounds: int = 5,
    initial_report_path: Path | None = None,
    stryker_bin: str = "dotnet-stryker",
    cwd: Path | None = None,
    log: Callable[[str], None] = print,
) -> None:
    """Drive the deterministic survivor-kill loop for one source file.

    ``generate`` is the sole non-deterministic step; each round's mechanics
    (scoped run, scoring, duplicate/insert guards, build/test verification,
    revert-on-failure, commit-on-green, and the no-improvement stop) live in
    :func:`_run_round` (#1561). This function only threads the round number
    and the previous survivor count across the ``for`` loop.
    """
    ctx = RunContext(
        source_file=source_file,
        config=config,
        test_file=test_file,
        source_path=source_path,
        output_dir=output_dir,
        generate=generate,
        initial_report_path=initial_report_path,
        stryker_bin=stryker_bin,
        cwd=cwd,
        log=log,
    )
    prev_survivor_count: int | None = None

    for round_num in range(1, max_rounds + 1):
        result = _run_round(round_num, prev_survivor_count, ctx)
        if result.stop:
            return
        prev_survivor_count = result.survivor_count
