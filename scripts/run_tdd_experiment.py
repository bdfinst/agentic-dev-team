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

# Markers used to estimate rework from a transcript when one is captured. These
# are best-effort heuristics, NOT an instrumented sensor -- the experiment doc
# flags rework_cycles as un-sensored and this is how we approximate it.
REWORK_MARKERS = (
    re.compile(r"review-fix loop|auto-fix iteration|re-?review", re.I),
    re.compile(r"\bRED\b.*restart|restart from RED", re.I),
    re.compile(r"tests? failed|FAILED|exit code [1-9]", re.I),
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    return env


def dispatch(workdir: Path, prompt: str, model: str, env: dict,
             transcript: Path | None) -> None:
    """Fresh, isolated `claude -p` dispatch. No session resume == no carryover."""
    cmd = ["claude", "-p", prompt, "--model", model]
    out = open(transcript, "w") if transcript else subprocess.DEVNULL
    try:
        subprocess.run(cmd, cwd=str(workdir), env=env, check=False,
                       stdout=out, stderr=subprocess.STDOUT)
    finally:
        if transcript:
            out.close()


def read_cost(home: Path) -> dict:
    """Best-effort: sum tokens/usd from this cell's private cost meter.

    Reads <home>/metrics/cost-metering.jsonl. The exact file the deployed
    cost-meter hook writes may differ; this scans the private root so whatever it
    writes there is attributed to this cell and nothing else.
    """
    total = {"tokens_total": 0, "cost_usd": 0.0, "found": False}
    meter = home / "metrics" / "cost-metering.jsonl"
    if not meter.exists():
        return total
    for line in meter.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        total["found"] = True
        tok = rec.get("tokens") or {}
        total["tokens_total"] += int(tok.get("total", 0) or 0)
        total["cost_usd"] += float(rec.get("cost_usd", 0) or 0)
    return total


def parse_rework(transcript: Path | None) -> dict:
    """Approximate rework signals from a captured transcript (best-effort)."""
    flags = {"review_fix_loops": 0, "red_restarts": 0, "failed_runs": 0,
             "transcript": False}
    if not transcript or not transcript.exists():
        return flags
    flags["transcript"] = True
    text = transcript.read_text(errors="ignore")
    flags["review_fix_loops"] = len(REWORK_MARKERS[0].findall(text))
    flags["red_restarts"] = len(REWORK_MARKERS[1].findall(text))
    flags["failed_runs"] = len(REWORK_MARKERS[2].findall(text))
    return flags


def contamination_flags(home: Path, transcript: Path | None) -> list[str]:
    """Cheap checks that isolation actually held for this cell."""
    flags: list[str] = []
    # A summarization means the window filled -> the run is a confound.
    if transcript and transcript.exists():
        if re.search(r"context.{0,12}summariz", transcript.read_text(errors="ignore"), re.I):
            flags.append("context_summarization_detected")
    # The private metrics file should contain only THIS cell's session(s).
    meter = home / "metrics" / "cost-metering.jsonl"
    if meter.exists():
        sessions = {json.loads(ln).get("session_id")
                    for ln in meter.read_text().splitlines()
                    if ln.strip() and _is_json(ln)}
        sessions.discard(None)
        if len(sessions) > 2:  # stage1 + stage2 at most per home reuse
            flags.append(f"unexpected_session_count={len(sessions)}")
    return flags


def _is_json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except json.JSONDecodeError:
        return False


def run_stage(stem: str, stage: str, prompt: str, fixture_dir: Path,
              espec: dict, run_root: Path, arm: str, trial: int,
              model: str, skip_dispatch: bool, capture: bool,
              seed_worktree: Path | None) -> dict:
    """Run one stage of one cell in full isolation; return a result row."""
    cell_id = f"{stem}__{arm}__t{trial}__{stage}"
    home = make_cell_home(run_root, cell_id)
    env = cell_env(home)
    transcript = (run_root / "transcripts" / f"{cell_id}.log") if capture else None
    if transcript:
        transcript.parent.mkdir(parents=True, exist_ok=True)

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

        if not skip_dispatch:
            doc = espec["change"] if stage == "change" else espec["spec"]
            if (fixture_dir / doc).exists():
                shutil.copy2(fixture_dir / doc, workdir / doc)
            dispatch(workdir, prompt.format(spec=espec.get("spec", ""),
                                            change=espec.get("change", "")),
                     model, env, transcript)

        results = run_commands(workdir, commands)
        passed = all(r["exit_code"] == 0 for r in results) and bool(results)
        row = {
            "ts": _utc(), "task": stem, "arm": arm, "trial": trial,
            "stage": stage, "model": model, "passed": passed,
            "results": results,
            "cost": read_cost(home),
            "rework": parse_rework(transcript),
            "contamination": contamination_flags(home, transcript),
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
