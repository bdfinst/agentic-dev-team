#!/usr/bin/env python3
"""TDD vs. test-after experiment runner.

Validates the question in docs/experiments/tdd-vs-test-after-experiment.md:
does the test-first workflow produce cheaper, better-tested, easier-to-change
code than writing tests at the end?

It reuses the integration-eval worktree primitives (run_integration_eval.py) but
adds the three things a *comparison* needs and the integration tier does not:

  1. ISOLATION — every (task x arm x trial x stage) cell runs in its own
     ephemeral worktree AND its own scratch HOME/config/metrics root, so no two
     cells can share a context window, a memory/ dir, or append to the same
     cost-metering.jsonl (concurrent appends corrupt cost attribution). A cell is
     a *fresh* dispatch: there is no session resume, so context cannot leak.
  2. TWO STAGES — Stage 1 builds the feature from a frozen spec; Stage 2 applies
     a WITHHELD change (revealed only at Stage 2) on top of the Stage-1 worktree,
     dispatched as a brand-new session that sees the Stage-1 *files* but none of
     its reasoning. Stage-2 cost/rework is the "easy to change" signal.
  3. REPLICATION — each cell runs --trials times; per-cell cost/coverage/rework
     are written to a JSONL the analysis step aggregates per task (the unit of
     inference) per arm.

Run with --skip-dispatch for a harness self-test: stages run no model, test
commands execute against the golden repo as-is, isolation still happens so the
plumbing is exercised. Grading stays model-free downstream.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# Reuse the audited integration primitives rather than reimplementing them.
from run_integration_eval import (  # noqa: E402
    extract_golden_repo,
    init_worktree,
    run_commands,
)

ARMS = ("test-first", "test-after")

# Arm-specific dispatch instructions. Everything else (spec, plan, reviews,
# model, golden repo) is held constant so the only variable is *when* tests are
# written -- see the fairness rules in the experiment doc.
ARM_PROMPTS = {
    "test-first": (
        "Implement the spec in {spec} using the full plan -> build -> review "
        "pipeline with strict TDD: every change is RED (failing test first) -> "
        "GREEN (minimum code) -> REFACTOR. Make the declared test commands pass."
    ),
    "test-after": (
        "Implement the spec in {spec} using the full plan -> build -> review "
        "pipeline. Write ALL production code first with NO test files. Only once "
        "the implementation is complete, author a test suite covering the same "
        "acceptance criteria to the same coverage target. Make the declared test "
        "commands pass."
    ),
}

CHANGE_PROMPT = (
    "This is an existing, already-implemented feature in the working directory. "
    "Apply the change described in {change}. Keep the existing test suite green; "
    "it is your safety net. Make the declared test commands pass."
)

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def contamination_flags(home: Path, cost: dict) -> list[str]:
    """Cheap checks that isolation/dispatch were sane for this cell.

    With nested dispatch the rework signal we get for free is num_turns; a wildly
    high count flags thrash worth inspecting. is_error flags a dispatch that did
    not complete cleanly. Filesystem isolation is structural (private worktree +
    HOME), so there is no shared meter to cross-check here.
    """
    flags: list[str] = []
    if cost.get("is_error"):
        flags.append("dispatch_error")
    turns = cost.get("num_turns")
    if isinstance(turns, int) and turns >= 40:
        flags.append(f"high_turn_count={turns}")
    return flags


def make_cell_home(run_root: Path, cell_id: str) -> Path:
    """Create an isolated HOME/config/metrics root for one cell.

    Pointing HOME, CLAUDE_CONFIG_DIR, and the metrics/memory dirs at a fresh,
    empty tree is what prevents context/cost corruption across cells: the plugin
    writes session cost to <root>/metrics/cost-metering.jsonl, so a private root
    means the session total *is* this cell's cost with no interleaving.
    """
    home = run_root / "homes" / cell_id
    (home / "metrics").mkdir(parents=True, exist_ok=True)
    (home / "memory").mkdir(parents=True, exist_ok=True)
    return home


def cell_env(home: Path) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    # Keep the opt-in telemetry beacon from bleeding state across cells.
    env.setdefault("DEV_TEAM_TELEMETRY", "off")
    # Each cell is a throwaway temp worktree; mark it a sandbox so headless
    # --dangerously-skip-permissions is allowed (the CLI blocks it under root
    # otherwise). Safe because the dispatch can only touch its own worktree.
    env["IS_SANDBOX"] = "1"
    return env


def dispatch(workdir: Path, prompt: str, model: str, env: dict,
             raw_out: Path | None) -> dict:
    """Fresh, isolated `claude -p` dispatch. No session resume == no carryover.

    Uses --output-format json: the result object carries the VERIFIED cost and
    token usage for this dispatch (the plugin cost-meter hook does not fire in a
    nested dispatch, so we read the native result instead). Returns a normalized
    cost dict.
    """
    # Each cell is a throwaway temp worktree, so headless edits are safe here.
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json",
           "--dangerously-skip-permissions"]
    proc = subprocess.run(cmd, cwd=str(workdir), env=env, check=False,
                          capture_output=True, text=True)
    if raw_out:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(proc.stdout or "")
    cost = {"cost_usd": None, "tokens_total": None, "input_tokens": None,
            "output_tokens": None, "num_turns": None, "duration_ms": None,
            "is_error": True, "parsed": False}
    try:
        d = json.loads(proc.stdout)
        u = d.get("usage", {}) or {}
        inp = (int(u.get("input_tokens", 0) or 0)
               + int(u.get("cache_creation_input_tokens", 0) or 0)
               + int(u.get("cache_read_input_tokens", 0) or 0))
        out = int(u.get("output_tokens", 0) or 0)
        cost.update(cost_usd=d.get("total_cost_usd"), input_tokens=inp,
                    output_tokens=out, tokens_total=inp + out,
                    num_turns=d.get("num_turns"), duration_ms=d.get("duration_ms"),
                    is_error=bool(d.get("is_error")), parsed=True)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return cost


# A file is "a test the agent wrote" if its name looks like a test and it was not
# one of the hidden acceptance files we inject at grading time.
TEST_NAME = re.compile(r"(^test_|_test\.|\.test\.|(^|/)tests?/|_spec\.|\.spec\.)", re.I)


def count_agent_tests(workdir: Path, injected: set[str]) -> int:
    """Manipulation check: how many test files exist that the AGENT authored."""
    n = 0
    for p in workdir.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        if p.name in injected:
            continue
        if TEST_NAME.search(p.name) or TEST_NAME.search(str(p.relative_to(workdir))):
            n += 1
    return n


def inject_grade_files(fixture_dir: Path, workdir: Path,
                       files: list[str]) -> set[str]:
    """Copy hidden acceptance files into the worktree AFTER dispatch.

    Acceptance tests must never be present during the build, or both arms would
    just make the given tests pass and the 'did they write good tests' signal
    would be destroyed. They are injected only at grading time.
    """
    injected: set[str] = set()
    for f in files:
        src = fixture_dir / f
        if src.exists():
            shutil.copy2(src, workdir / Path(f).name)
            injected.add(Path(f).name)
    return injected


def run_stage(stem: str, stage: str, prompt: str, fixture_dir: Path,
              espec: dict, run_root: Path, arm: str, trial: int,
              model: str, skip_dispatch: bool, capture: bool,
              seed_worktree: Path | None) -> dict:
    """Run one stage of one cell in full isolation; return a result row."""
    cell_id = f"{stem}__{arm}__t{trial}__{stage}"
    home = make_cell_home(run_root, cell_id)
    env = cell_env(home)
    raw_out = (run_root / "raw" / f"{cell_id}.json") if capture else None

    workdir = Path(tempfile.mkdtemp(prefix=f"exp-{cell_id}-"))
    try:
        if seed_worktree is not None:
            # Stage 2 builds ON TOP of the Stage-1 output (files only, no context).
            shutil.copytree(seed_worktree, workdir, dirs_exist_ok=True)
        else:
            extract_golden_repo(fixture_dir / espec["goldenRepo"], workdir)
            init_worktree(workdir)

        commands_key = "changeTestCommands" if stage == "change" else "testCommands"
        commands = espec.get(commands_key, [])
        grade_key = "changeGradeFiles" if stage == "change" else "gradeFiles"
        grade_files = espec.get(grade_key, [])

        cost = {"parsed": False}
        if not skip_dispatch:
            doc = espec["change"] if stage == "change" else espec["spec"]
            if (fixture_dir / doc).exists():
                shutil.copy2(fixture_dir / doc, workdir / Path(doc).name)
            cost = dispatch(workdir, prompt.format(spec=espec.get("spec", ""),
                                                   change=espec.get("change", "")),
                            model, env, raw_out)

        # Count agent-authored tests BEFORE injecting hidden acceptance files.
        agent_tests = count_agent_tests(workdir, injected=set())
        inject_grade_files(fixture_dir, workdir, grade_files)

        results = run_commands(workdir, commands)
        passed = all(r["exit_code"] == 0 for r in results) and bool(results)
        row = {
            "ts": _utc(), "task": stem, "arm": arm, "trial": trial,
            "stage": stage, "model": model, "passed": passed,
            "results": results,
            "cost": cost,
            "agent_test_files": agent_tests,
            "contamination": contamination_flags(home, cost),
        }
        # Stage 1 keeps its worktree so Stage 2 can seed from it.
        row["_worktree"] = str(workdir) if stage == "build" else None
        return row
    finally:
        if stage != "build":
            shutil.rmtree(workdir, ignore_errors=True)


def run_cell(stem: str, espec: dict, fixture_dir: Path, run_root: Path,
             arm: str, trial: int, model: str, skip_dispatch: bool,
             capture: bool, two_stage: bool) -> list[dict]:
    rows = []
    build = run_stage(stem, "build", ARM_PROMPTS[arm], fixture_dir, espec,
                      run_root, arm, trial, model, skip_dispatch, capture,
                      seed_worktree=None)
    seed = Path(build.pop("_worktree")) if build.get("_worktree") else None
    rows.append(build)
    try:
        if two_stage and espec.get("change"):
            change = run_stage(stem, "change", CHANGE_PROMPT, fixture_dir, espec,
                               run_root, arm, trial, model, skip_dispatch,
                               capture, seed_worktree=seed)
            change.pop("_worktree", None)
            rows.append(change)
    finally:
        if seed is not None:
            shutil.rmtree(seed, ignore_errors=True)
    return rows


def load_experiments(exp_dir: Path, only: set[str] | None) -> list[tuple[str, dict]]:
    out = []
    for ef in sorted(exp_dir.glob("*.json")):
        if ef.name == "exp-tdd-template.json":
            continue
        spec = json.loads(ef.read_text())
        block = spec.get("experiment")
        if not block:
            continue
        if only and ef.stem not in only:
            continue
        out.append((ef.stem, block))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=ARMS, action="append",
                    help="arm(s) to run; repeat for both (default: both)")
    ap.add_argument("--trials", type=int, default=1,
                    help="trials per (task x arm); pilot then power-calc this up")
    ap.add_argument("--experiments-dir", default="evals/experiments")
    ap.add_argument("--fixtures-dir", default="evals/fixtures")
    ap.add_argument("--run-root", default="",
                    help="scratch root for isolated homes/transcripts "
                         "(default: a fresh temp dir, kept for inspection)")
    ap.add_argument("--out", default="metrics/tdd-experiment.jsonl")
    ap.add_argument("--only", default="", help="comma-separated task stems")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--one-stage", action="store_true",
                    help="skip the Stage-2 change (build only)")
    ap.add_argument("--skip-dispatch", action="store_true",
                    help="harness self-test: isolate + run commands, no model")
    ap.add_argument("--no-capture", action="store_true",
                    help="do not capture transcripts (disables rework parsing)")
    args = ap.parse_args(argv)

    if not args.skip_dispatch and shutil.which("claude") is None:
        print("error: `claude` CLI not found; pass --skip-dispatch for a "
              "harness self-test", file=sys.stderr)
        return 2

    arms = tuple(dict.fromkeys(args.arm)) if args.arm else ARMS
    exp_dir = Path(args.experiments_dir)
    fixtures_dir = Path(args.fixtures_dir)
    if not exp_dir.is_dir():
        print(f"error: experiments dir not found: {exp_dir}", file=sys.stderr)
        return 2
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    experiments = load_experiments(exp_dir, only)
    if not experiments:
        print("error: no experiment fixtures found (need an 'experiment' block)",
              file=sys.stderr)
        return 2

    run_root = Path(args.run_root) if args.run_root else \
        Path(tempfile.mkdtemp(prefix="tdd-exp-run-"))
    run_root.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    with out_path.open("a") as fh:
        for stem, espec in experiments:
            fixture_dir = fixtures_dir / stem
            for arm in arms:
                for trial in range(1, args.trials + 1):
                    print(f"· {stem} :: {arm} :: trial {trial}"
                          f"{' (no-dispatch)' if args.skip_dispatch else ''}",
                          file=sys.stderr)
                    rows = run_cell(stem, espec, fixture_dir, run_root, arm,
                                    trial, args.model, args.skip_dispatch,
                                    capture=not args.no_capture,
                                    two_stage=not args.one_stage)
                    for row in rows:
                        fh.write(json.dumps(row) + "\n")
                        rows_written += 1

    print(f"experiment runner: {rows_written} row(s) → {out_path}",
          file=sys.stderr)
    print(f"isolated run root kept at: {run_root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
