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
import ast
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

# A constraint applied EQUALLY to both arms so the coverage/mutation sensors can
# run on whatever tests the agent wrote. It does not bias the when-to-test
# variable; it only standardizes how tests are invoked.
PYTEST_RULE = (
    " Write your tests as pytest tests in a file named test_*.py so they run "
    "with `python -m pytest -q`. Put production code in the module named in the "
    "spec."
)

# Arm-specific dispatch instructions. Everything else (spec, plan, reviews,
# model, golden repo) is held constant so the only variable is *when* tests are
# written -- see the fairness rules in the experiment doc.
ARM_PROMPTS = {
    "test-first": (
        "Implement the spec in {spec} using strict TDD: every change is RED "
        "(write a failing test first) -> GREEN (minimum code to pass) -> "
        "REFACTOR. Make the acceptance behavior correct." + PYTEST_RULE
    ),
    "test-after": (
        "Implement the spec in {spec}. Write ALL production code first with NO "
        "test files. Only once the implementation is complete, author a test "
        "suite covering the same behavior. Make the acceptance behavior correct."
        + PYTEST_RULE
    ),
}

CHANGE_PROMPT = (
    "This is an existing, already-implemented feature in the working directory. "
    "Apply the change described in {change}. Keep the existing test suite green; "
    "it is your safety net." + PYTEST_RULE
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


def split_py_files(workdir: Path) -> tuple[list[Path], list[Path]]:
    """Return (production_files, test_files) the agent authored in the worktree."""
    prod, tests = [], []
    for p in sorted(workdir.rglob("*.py")):
        if ".git" in p.parts or "__pycache__" in p.parts:
            continue
        rel = str(p.relative_to(workdir))
        (tests if (TEST_NAME.search(p.name) or TEST_NAME.search(rel)) else prod).append(p)
    return prod, tests


def measure_coverage(workdir: Path, env: dict, prod: list[Path]) -> dict:
    """Branch coverage of the AGENT's production code by the AGENT's own tests.

    Runs `coverage run --branch -m pytest`, writes a JSON report, and averages
    percent_covered over the production files only (test files are excluded).
    Self-coverage is one half of the 'fully tested' axis; mutation score is the
    other (coverage can be high with weak assertions).
    """
    out = {"percent": None, "tests_passed": None}
    if not prod:
        return out
    cov_env = dict(env)
    cov_env["COVERAGE_FILE"] = str(workdir / ".coverage")
    run = subprocess.run(
        ["python3", "-m", "coverage", "run", "--branch", "--source=.",
         "-m", "pytest", "-q"],
        cwd=str(workdir), env=cov_env, capture_output=True, text=True)
    out["tests_passed"] = (run.returncode == 0)
    subprocess.run(
        ["python3", "-m", "coverage", "json", "-o", str(workdir / "cov.json")],
        cwd=str(workdir), env=cov_env, capture_output=True, text=True)
    try:
        data = json.loads((workdir / "cov.json").read_text())
        prod_names = {str(p.relative_to(workdir)) for p in prod}
        pcts = [f["summary"]["percent_covered"]
                for name, f in data["files"].items()
                if name in prod_names or Path(name).name in
                {p.name for p in prod}]
        if pcts:
            out["percent"] = round(sum(pcts) / len(pcts), 1)
    except (json.JSONDecodeError, KeyError, ValueError, FileNotFoundError):
        pass
    (workdir / "cov.json").unlink(missing_ok=True)
    (workdir / ".coverage").unlink(missing_ok=True)
    return out


# AST-level mutation operators. Operating on the parse tree (not text) reliably
# catches operators regardless of whitespace and never mutates strings/comments.
_BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div,
          ast.Div: ast.Mult}
_CMPOP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
          ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_BOOLOP = {ast.And: ast.Or, ast.Or: ast.And}


def _mutation_sites(tree: ast.AST) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
            n += 1
        elif isinstance(node, ast.Compare):
            n += sum(type(o) in _CMPOP for o in node.ops)
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOLOP:
            n += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            n += 1
    return n


def _apply_mutation(src: str, k: int) -> str | None:
    """Return source with the k-th mutation site flipped, or None if invalid."""
    tree = ast.parse(src)
    counter = {"i": 0}

    def flip(node) -> bool:
        i = counter["i"]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
            if i == k:
                node.op = _BINOP[type(node.op)]()
                return True
            counter["i"] += 1
        elif isinstance(node, ast.Compare):
            for j, o in enumerate(node.ops):
                if type(o) in _CMPOP:
                    if counter["i"] == k:
                        node.ops[j] = _CMPOP[type(o)]()
                        return True
                    counter["i"] += 1
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOLOP:
            if i == k:
                node.op = _BOOLOP[type(node.op)]()
                return True
            counter["i"] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            if i == k:
                node.value = not node.value
                return True
            counter["i"] += 1
        return False

    for node in ast.walk(tree):
        if flip(node):
            return ast.unparse(tree)
    return None


def measure_mutation(workdir: Path, env: dict, prod: list[Path],
                     cap: int = 40) -> dict:
    """Built-in AST mutation check on the agent's production code.

    For each mutation, re-run the agent's tests; non-zero exit == killed. A
    survivor is direct evidence of a weak/missing assertion. Capped for speed;
    requires the baseline suite to be green first.
    """
    out = {"killed": 0, "total": 0, "score": None, "baseline_green": None,
           "survivors": []}
    base = subprocess.run(["python3", "-m", "pytest", "-q"], cwd=str(workdir),
                          env=env, capture_output=True, text=True)
    out["baseline_green"] = (base.returncode == 0)
    if not out["baseline_green"]:
        return out

    jobs: list[tuple[Path, str, int]] = []
    originals = {p: p.read_text() for p in prod}
    for p, src in originals.items():
        try:
            sites = _mutation_sites(ast.parse(src))
        except SyntaxError:
            continue
        for k in range(sites):
            jobs.append((p, src, k))
    if len(jobs) > cap:  # deterministic even sample across files/sites
        step = len(jobs) / cap
        jobs = [jobs[int(i * step)] for i in range(cap)]

    try:
        for p, src, k in jobs:
            mutated = _apply_mutation(src, k)
            if mutated is None or mutated == src:
                continue
            p.write_text(mutated)
            r = subprocess.run(["python3", "-m", "pytest", "-q"],
                               cwd=str(workdir), env=env,
                               capture_output=True, text=True)
            p.write_text(src)
            out["total"] += 1
            if r.returncode != 0:
                out["killed"] += 1
            elif len(out["survivors"]) < 8:
                out["survivors"].append({"file": p.name, "site": k})
    finally:
        for p, src in originals.items():
            p.write_text(src)
    if out["total"]:
        out["score"] = round(out["killed"] / out["total"], 3)
    return out


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

        # Measure the AGENT's OWN tests BEFORE injecting hidden acceptance files
        # (coverage/mutation must judge the agent's suite, not the graded one).
        agent_tests = count_agent_tests(workdir, injected=set())
        prod, _tests = ([], []) if skip_dispatch else split_py_files(workdir)
        coverage = measure_coverage(workdir, env, prod) if prod else {"percent": None}
        mutation = measure_mutation(workdir, env, prod) if prod else {"score": None}

        inject_grade_files(fixture_dir, workdir, grade_files)
        results = run_commands(workdir, commands)
        passed = all(r["exit_code"] == 0 for r in results) and bool(results)
        row = {
            "ts": _utc(), "task": stem, "arm": arm, "trial": trial,
            "stage": stage, "model": model, "passed": passed,
            "results": results,
            "cost": cost,
            "agent_test_files": agent_tests,
            "self_coverage": coverage,
            "mutation": mutation,
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
