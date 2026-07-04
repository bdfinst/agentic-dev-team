#!/usr/bin/env python3
"""When-does-TDD-pay-off experiment runner.

Extends run_tdd_experiment.py with:
  - clarity selection (clear / vague spec per cell)
  - CORE/EDGE split grading at Stage 0
  - withheld K-stage change chain, each seeded from the prior stage
  - blast-radius measurement (git diff lines/files between stages)
  - radon cc/mi structural metrics per production module per stage
  - K=3 multi-rater review panel at the final stage
  - test-after-refactor arm: write code → tests against working impl → refactor
  - ship arm (plugin): /specs→/plan→/build pipeline (vague only)

Design matrix — second run adds test-after-refactor and ship (9 cells per task):
  clear × {tdd-refactor, test-after, test-after-refactor}          (anchors)
  vague × {tdd-refactor, tdd-no-refactor, test-after,              (full set)
            test-after-refactor, bduf, ship}

Pre-registration (from experiment spec):
  N = 3 trials/cell
  Primary 1: EDGE pass rate under vague (tdd-refactor vs test-after, Wilcoxon)
  Primary 2: cumulative changeability (tokens + blast-radius across chain)
  clarity-interaction: interaction — is tdd-refactor margin largest in vague+open-design cell?
  spec-synthesis: ship vs tdd-refactor EDGE + changeability under vague
  test-after-refactor: test-after-refactor dominance (EDGE ≥ test-after, blast ≈ tdd-refactor,
         cost < tdd-refactor) — all three must hold
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
from statistics import mean, stdev

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from run_integration_eval import extract_golden_repo, init_worktree, run_commands
from run_tdd_experiment import (
    contamination_flags, make_cell_home, cell_env, dispatch,
    count_agent_tests, split_py_files, measure_coverage, measure_mutation,
    inject_grade_files, TEST_NAME,
)

MODEL_DEFAULT = "claude-sonnet-4-6"
REVIEW_PASSES = 3  # K-rater panel

# Arms that need a plugin-enabled HOME (the ship arm runs /specs→/plan→/build)
PLUGIN_ARMS = frozenset({"ship"})

PYTEST_RULE = (
    " Write your tests as pytest tests in a file named test_*.py so they run "
    "with `python -m pytest -q`. Put production code in the module named in the "
    "spec."
)

ARM_PROMPTS = {
    "tdd-refactor": (
        "Implement the spec in {spec} using strict TDD with mandatory refactoring: "
        "for EACH behavior, write a FAILING test first (RED), write the MINIMUM code "
        "to make it pass (GREEN), then REFACTOR toward the cleanest module "
        "boundaries, naming, and elimination of duplication — re-run tests to stay "
        "green — THEN write the next failing test. Do NOT defer refactoring; it is "
        "required after every green. Make the acceptance behavior correct."
        + PYTEST_RULE
    ),
    "tdd-no-refactor": (
        "Implement the spec in {spec} using test-first development WITHOUT "
        "refactoring: write a FAILING test (RED), write the MINIMUM code to pass it "
        "(GREEN), then immediately move on to the next test. Do NOT restructure, "
        "rename, or reorganize anything once tests pass. Make the acceptance "
        "behavior correct." + PYTEST_RULE
    ),
    "test-after": (
        "Implement the spec in {spec}. Write ALL production code first with NO test "
        "files. Only once the implementation is complete, author a test suite "
        "covering the behavior. Make the acceptance behavior correct." + PYTEST_RULE
    ),
    "test-after-refactor": (
        "Implement the spec in {spec} in three ordered phases. "
        "Phase 1 — WRITE ALL PRODUCTION CODE FIRST: implement the complete feature "
        "with no test files at all. Do not write a single test until the production "
        "implementation is working. "
        "Phase 2 — WRITE TESTS AGAINST THE WORKING IMPLEMENTATION: now that you can "
        "see the full shape of the problem, author a test suite that captures the "
        "actual contract the implementation delivers — including edge behaviours that "
        "only became clear while building. Do not write tests before Phase 1 is done. "
        "Phase 3 — REFACTOR WITH THE TEST SAFETY NET: with all tests green, refactor "
        "toward cleaner module boundaries, better naming, and elimination of "
        "duplication. Re-run tests after every refactor step; stay green. "
        "Make the acceptance behavior correct." + PYTEST_RULE
    ),
    "bduf": (
        "Implement the spec in {spec} using Big Design Up Front: FIRST write a "
        "short DESIGN.md that specifies the module structure, class names, and "
        "public interfaces you intend to implement. THEN implement the spec to that "
        "design exactly. THEN write the tests. Make the acceptance behavior correct."
        + PYTEST_RULE
    ),
    "ship": (
        "You are operating FULLY AUTONOMOUSLY with no human reviewer present. "
        "Use the dev-team plugin's full pipeline to implement the spec in {spec}: "
        "run /specs to author explicit acceptance criteria from the spec (including "
        "every edge-case decision the spec omitted — you must state your choices), "
        "then IMMEDIATELY approve your own specs yourself and run /plan, "
        "then IMMEDIATELY approve your own plan yourself and run /build to "
        "implement with RED-GREEN-REFACTOR and inline review checkpoints. "
        "NEVER stop to ask for approval or confirmation — approve and proceed "
        "every time. Make the acceptance behavior correct." + PYTEST_RULE
    ),
}

CHANGE_PROMPTS = {
    "tdd-refactor": (
        "This is an existing, already-implemented feature in the working directory. "
        "Apply the change described in {change} using strict TDD with mandatory "
        "refactoring: RED → GREEN → REFACTOR after every green. Keep the existing "
        "test suite green throughout; it is your safety net." + PYTEST_RULE
    ),
    "tdd-no-refactor": (
        "This is an existing, already-implemented feature in the working directory. "
        "Apply the change described in {change} using test-first WITHOUT refactoring: "
        "RED → GREEN only, never restructure. Keep the existing test suite green."
        + PYTEST_RULE
    ),
    "test-after": (
        "This is an existing, already-implemented feature in the working directory. "
        "Apply the change described in {change}. Update the production code, then "
        "update or add tests. Keep the existing test suite green." + PYTEST_RULE
    ),
    "test-after-refactor": (
        "This is an existing, already-implemented feature in the working directory. "
        "Apply the change described in {change} in three phases: "
        "Phase 1 — update the production code to implement the change. "
        "Phase 2 — update or extend the tests to cover the new behavior. "
        "Phase 3 — refactor with all tests green; keep the suite green throughout."
        + PYTEST_RULE
    ),
    "bduf": (
        "This is an existing, already-implemented feature in the working directory. "
        "Apply the change described in {change}. First update DESIGN.md to reflect "
        "the new design, then implement, then update tests. Keep the existing test "
        "suite green." + PYTEST_RULE
    ),
    "ship": (
        "You are operating FULLY AUTONOMOUSLY with no human reviewer present. "
        "This is an existing feature in the working directory. "
        "Apply the change described in {change} using the dev-team pipeline: "
        "run /plan to plan the change, IMMEDIATELY approve your own plan, "
        "then run /build with RED-GREEN-REFACTOR. Keep the existing test suite "
        "green. NEVER stop to ask for approval — approve and proceed every time."
        + PYTEST_RULE
    ),
}

# First-run cells (4 arms × 6 cells per task).
# Second-run cells add test-after-refactor (both clarities) + ship (vague only).
# Use --run=first, --run=second, or --run=all to select.
_FIRST_RUN = [
    ("tdd-refactor", "clear"), ("test-after", "clear"),
    ("tdd-refactor", "vague"), ("tdd-no-refactor", "vague"),
    ("test-after", "vague"), ("bduf", "vague"),
]
_SECOND_RUN = [
    ("test-after-refactor", "clear"),
    ("test-after-refactor", "vague"),
    ("ship", "vague"),
]

CLARITY_PAIRS = {
    "clear": [("tdd-refactor", "clear"), ("test-after", "clear"),
              ("test-after-refactor", "clear")],
    "vague": [("tdd-refactor", "vague"), ("tdd-no-refactor", "vague"),
              ("test-after", "vague"), ("test-after-refactor", "vague"),
              ("bduf", "vague"), ("ship", "vague")],
    "both": _FIRST_RUN + _SECOND_RUN,
    "first": _FIRST_RUN,
    "second": _SECOND_RUN,
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── git utilities ─────────────────────────────────────────────────────────────

def _git_commit_all(workdir: Path, message: str) -> str | None:
    """Commit all current files and return the commit sha, or None on failure."""
    quiet = {"cwd": str(workdir), "capture_output": True, "text": True}
    try:
        subprocess.run(["git", "add", "-A"], **quiet, check=True)
        subprocess.run(
            ["git", "-c", "user.email=exp@dev-team", "-c", "user.name=exp",
             "commit", "-m", message, "--allow-empty"], **quiet, check=True)
        r = subprocess.run(["git", "rev-parse", "HEAD"], **quiet, check=True)
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def measure_blast_radius(workdir: Path, from_sha: str | None) -> dict:
    """Measure structural change between from_sha and HEAD."""
    out = {"files_changed": None, "lines_added": None, "lines_deleted": None,
           "api_churn": None}
    if from_sha is None:
        return out
    try:
        stat = subprocess.run(
            ["git", "diff", "--stat", from_sha, "HEAD"],
            cwd=str(workdir), capture_output=True, text=True, check=False)
        lines = stat.stdout.strip().split("\n")
        # last line: "N files changed, X insertions(+), Y deletions(-)"
        if lines:
            summary = lines[-1]
            m = re.search(r"(\d+) file", summary)
            out["files_changed"] = int(m.group(1)) if m else None
            m = re.search(r"(\d+) insertion", summary)
            out["lines_added"] = int(m.group(1)) if m else 0
            m = re.search(r"(\d+) deletion", summary)
            out["lines_deleted"] = int(m.group(1)) if m else 0
        # Detect public-API churn: check for def/class changes in non-test modules
        name_re = subprocess.run(
            ["git", "diff", from_sha, "HEAD", "--", "*.py"],
            cwd=str(workdir), capture_output=True, text=True, check=False)
        api_lines = [l for l in name_re.stdout.split("\n")
                     if l.startswith(("+def ", "-def ", "+class ", "-class "))]
        out["api_churn"] = len(api_lines)
    except (subprocess.CalledProcessError, OSError, ValueError):
        pass
    return out


# ── radon metrics ─────────────────────────────────────────────────────────────

def measure_radon(workdir: Path, prod: list[Path]) -> dict:
    """Compute radon cc (avg cyclomatic complexity) and mi (maintainability index)."""
    out = {"avg_cc": None, "avg_mi": None, "files_measured": 0}
    if not prod or not shutil.which("radon"):
        return out
    cc_scores: list[float] = []
    mi_scores: list[float] = []
    for p in prod:
        try:
            r = subprocess.run(["radon", "cc", "-s", "-a", str(p)],
                               capture_output=True, text=True, cwd=str(workdir))
            for line in r.stdout.split("\n"):
                m = re.search(r"Average complexity: [A-F] \((\d+\.\d+)\)", line)
                if m:
                    cc_scores.append(float(m.group(1)))
            r2 = subprocess.run(["radon", "mi", "-s", str(p)],
                                capture_output=True, text=True, cwd=str(workdir))
            for line in r2.stdout.split("\n"):
                m2 = re.search(r"\((\d+\.\d+)\)", line)
                if m2:
                    mi_scores.append(float(m2.group(1)))
        except (subprocess.CalledProcessError, OSError, ValueError):
            pass
    out["files_measured"] = len(prod)
    if cc_scores:
        out["avg_cc"] = round(mean(cc_scores), 2)
    if mi_scores:
        out["avg_mi"] = round(mean(mi_scores), 2)
    return out


def _test_code_ratio(workdir: Path, prod: list[Path], tests: list[Path]) -> dict:
    """Count non-blank, non-comment lines in prod vs test files."""
    def _loc(paths: list[Path]) -> int:
        total = 0
        for p in paths:
            try:
                for line in p.read_text(errors="replace").splitlines():
                    s = line.strip()
                    if s and not s.startswith("#"):
                        total += 1
            except OSError:
                pass
        return total

    prod_loc = _loc(prod)
    test_loc = _loc(tests)
    ratio = round(test_loc / prod_loc, 2) if prod_loc else None
    return {"prod_loc": prod_loc, "test_loc": test_loc, "ratio": ratio}


# ── multi-rater review ────────────────────────────────────────────────────────

REVIEW_PROMPT_TPL = """You are a senior code reviewer. Review the Python code below and rate it on each dimension from 0–10 (integers only). Output ONLY a JSON object with these keys: structure, complexity, naming, performance, test_quality. No explanation.

{code}
"""


def _collect_code(workdir: Path, prod: list[Path], tests: list[Path]) -> str:
    """Concatenate production and test code for review."""
    parts: list[str] = []
    for p in prod[:4]:  # cap to avoid huge prompts
        try:
            parts.append(f"# --- {p.name} ---\n{p.read_text()}")
        except OSError:
            pass
    for p in tests[:2]:
        try:
            parts.append(f"# --- {p.name} (tests) ---\n{p.read_text()}")
        except OSError:
            pass
    return "\n\n".join(parts)[:12000]  # hard-cap at ~12k chars


def multi_rater_review(workdir: Path, prod: list[Path], tests: list[Path],
                       model: str, env: dict, k: int = REVIEW_PASSES) -> dict:
    """Run K review passes and return mean±stdev scores per dimension."""
    code = _collect_code(workdir, prod, tests)
    if not code.strip():
        return {}
    prompt = REVIEW_PROMPT_TPL.format(code=code)
    all_scores: dict[str, list[float]] = {}
    for _ in range(k):
        try:
            skip_flag = [] if os.getuid() == 0 else ["--dangerously-skip-permissions"]
            r = subprocess.run(
                ["claude", "-p", prompt, "--model", model,
                 "--output-format", "json", *skip_flag],
                cwd=str(workdir), env=env, capture_output=True, text=True, timeout=120)
            d = json.loads(r.stdout)
            result_text = d.get("result", "")
            m = re.search(r"\{[^}]+\}", result_text, re.DOTALL)
            if m:
                scores = json.loads(m.group())
                for k_name, v in scores.items():
                    all_scores.setdefault(k_name, []).append(float(v))
        except (json.JSONDecodeError, subprocess.TimeoutExpired,
                ValueError, OSError, AttributeError):
            pass
    summary: dict = {}
    for dim, vals in all_scores.items():
        summary[dim] = {
            "mean": round(mean(vals), 2),
            "stdev": round(stdev(vals), 2) if len(vals) > 1 else 0.0,
            "n": len(vals),
        }
    return summary


# ── stage runner ──────────────────────────────────────────────────────────────

def run_stage0(stem: str, arm: str, clarity: str, trial: int,
               espec: dict, fixture_dir: Path, run_root: Path,
               model: str, skip_dispatch: bool, capture: bool,
               plugin_template: Path | None = None) -> tuple[dict, Path | None]:
    """Build stage: dispatch then grade CORE and EDGE separately."""
    cell_id = f"{stem}__{arm}__{clarity}__t{trial}__stage0"
    tpl = plugin_template if arm in PLUGIN_ARMS else None
    home = make_cell_home(run_root, cell_id, tpl)
    env = cell_env(home)
    raw_out = (run_root / "raw" / f"{cell_id}.json") if capture else None

    workdir = Path(tempfile.mkdtemp(prefix=f"exp-{cell_id}-"))
    extract_golden_repo(fixture_dir / espec["goldenRepo"], workdir)
    init_worktree(workdir)
    base_sha = _git_commit_all(workdir, "baseline")

    spec_file = espec["specClear"] if clarity == "clear" else espec["specVague"]
    if (fixture_dir / spec_file).exists():
        shutil.copy2(fixture_dir / spec_file, workdir / spec_file)

    cost: dict = {"parsed": False}
    if not skip_dispatch:
        prompt = ARM_PROMPTS[arm].format(spec=spec_file, change="")
        cost = dispatch(workdir, prompt, model, env, raw_out)

    agent_tests = count_agent_tests(workdir, injected=set())
    prod, tests = ([], []) if skip_dispatch else split_py_files(workdir)
    coverage = measure_coverage(workdir, env, prod) if prod else {"percent": None}
    mutation = measure_mutation(workdir, env, prod) if prod else {"score": None}
    radon = measure_radon(workdir, prod)
    test_code_ratio = _test_code_ratio(workdir, prod, tests)

    # Commit after build for blast-radius baseline of change chain
    post_build_sha = _git_commit_all(workdir, "post-build")

    core_files = espec.get("coreGradeFiles", [])
    edge_files = espec.get("edgeGradeFiles", [])
    injected = inject_grade_files(fixture_dir, workdir, core_files + edge_files)
    core_results = run_commands(workdir, espec.get("coreTestCommands", []))
    edge_results = run_commands(workdir, espec.get("edgeTestCommands", []))

    row = {
        "ts": _utc(), "task": stem, "arm": arm, "clarity": clarity,
        "trial": trial, "stage": "stage0", "model": model,
        "core_passed": all(r["exit_code"] == 0 for r in core_results) and bool(core_results),
        "edge_passed": all(r["exit_code"] == 0 for r in edge_results) and bool(edge_results),
        "core_results": core_results, "edge_results": edge_results,
        "cost": cost, "agent_test_files": agent_tests,
        "self_coverage": coverage, "mutation": mutation, "test_code_ratio": test_code_ratio,
        "radon": radon, "contamination": contamination_flags(home, cost),
        "_worktree": str(workdir), "_post_build_sha": post_build_sha,
        "_prod_paths": [str(p) for p in prod],
        "_test_paths": [str(p) for p in tests],
    }
    return row, workdir


def run_change_stage(stem: str, arm: str, clarity: str, trial: int,
                     chain_idx: int, chain_spec: dict,
                     espec: dict, fixture_dir: Path, run_root: Path,
                     model: str, skip_dispatch: bool, capture: bool,
                     seed_worktree: Path, prior_sha: str | None,
                     is_last: bool, do_review: bool,
                     plugin_template: Path | None = None) -> tuple[dict, Path, str | None]:
    """One change-chain stage; returns (row, new_workdir, new_sha)."""
    stage_name = f"change{chain_idx + 1}"
    cell_id = f"{stem}__{arm}__{clarity}__t{trial}__{stage_name}"
    tpl = plugin_template if arm in PLUGIN_ARMS else None
    home = make_cell_home(run_root, cell_id, tpl)
    env = cell_env(home)
    raw_out = (run_root / "raw" / f"{cell_id}.json") if capture else None

    workdir = Path(tempfile.mkdtemp(prefix=f"exp-{cell_id}-"))
    shutil.copytree(seed_worktree, workdir, dirs_exist_ok=True)

    change_file = chain_spec["change"]
    if (fixture_dir / change_file).exists():
        shutil.copy2(fixture_dir / change_file, workdir / change_file)

    cost: dict = {"parsed": False}
    if not skip_dispatch:
        prompt = CHANGE_PROMPTS[arm].format(change=change_file, spec="")
        cost = dispatch(workdir, prompt, model, env, raw_out)

    prod, tests = ([], []) if skip_dispatch else split_py_files(workdir)

    # Measure coverage and test-to-code ratio before injecting grade files
    coverage = measure_coverage(workdir, env, prod) if prod else {"percent": None}
    test_code_ratio = _test_code_ratio(workdir, prod, tests)

    post_change_sha = _git_commit_all(workdir, f"post-{stage_name}")
    blast = measure_blast_radius(workdir, prior_sha)
    radon = measure_radon(workdir, prod)

    all_grade = (
        espec.get("coreGradeFiles", []) +
        espec.get("edgeGradeFiles", []) +
        chain_spec.get("gradeFiles", [])
    )
    inject_grade_files(fixture_dir, workdir, all_grade)
    results = run_commands(workdir, chain_spec.get("testCommands", []))

    review = {}
    if is_last and do_review and prod:
        review = multi_rater_review(workdir, prod, tests, model, env)

    row = {
        "ts": _utc(), "task": stem, "arm": arm, "clarity": clarity,
        "trial": trial, "stage": stage_name, "model": model,
        "passed": all(r["exit_code"] == 0 for r in results) and bool(results),
        "results": results, "cost": cost,
        "blast_radius": blast, "radon": radon,
        "self_coverage": coverage, "test_code_ratio": test_code_ratio,
        "multi_rater_review": review,
        "contamination": contamination_flags(home, cost),
    }
    return row, workdir, post_change_sha


def run_cell(stem: str, espec: dict, fixture_dir: Path, run_root: Path,
             arm: str, clarity: str, trial: int, model: str,
             skip_dispatch: bool, capture: bool, do_review: bool,
             plugin_template: Path | None = None) -> list[dict]:
    """Run one full cell: stage0 + full change chain; return all row dicts."""
    rows: list[dict] = []

    stage0_row, workdir0 = run_stage0(
        stem, arm, clarity, trial, espec, fixture_dir, run_root,
        model, skip_dispatch, capture, plugin_template=plugin_template)
    prior_sha = stage0_row.pop("_post_build_sha", None)
    stage0_row.pop("_prod_paths", [])
    stage0_row.pop("_test_paths", [])
    stage0_row.pop("_worktree", None)
    rows.append(stage0_row)

    chain = espec.get("changeChain", [])
    current_workdir = workdir0
    try:
        for i, chain_spec in enumerate(chain):
            is_last = (i == len(chain) - 1)
            change_row, new_workdir, new_sha = run_change_stage(
                stem, arm, clarity, trial, i, chain_spec,
                espec, fixture_dir, run_root, model, skip_dispatch, capture,
                seed_worktree=current_workdir, prior_sha=prior_sha,
                is_last=is_last, do_review=do_review,
                plugin_template=plugin_template)
            rows.append(change_row)
            if current_workdir != workdir0:
                shutil.rmtree(current_workdir, ignore_errors=True)
            current_workdir = new_workdir
            prior_sha = new_sha
    finally:
        shutil.rmtree(current_workdir, ignore_errors=True)
        if workdir0 is not None and workdir0.exists():
            shutil.rmtree(workdir0, ignore_errors=True)

    return rows


# ── experiment loader ─────────────────────────────────────────────────────────

def load_experiments(exp_dir: Path, only: set[str] | None,
                     prefix: str = "exp-tdd-pays-") -> list[tuple[str, dict]]:
    out = []
    for ef in sorted(exp_dir.glob(f"{prefix}*.json")):
        spec = json.loads(ef.read_text())
        block = spec.get("experiment")
        if not block:
            continue
        if only and ef.stem not in only:
            continue
        out.append((ef.stem, block))
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--clarity",
        choices=list(CLARITY_PAIRS),
        default="both",
        help="arm-clarity set: 'both' = all 9 cells (first+second run), "
             "'first' = original 6, 'second' = 3 new cells, "
             "or 'clear'/'vague' for a single clarity slice (default: both)",
    )
    ap.add_argument("--arm", choices=list(ARM_PROMPTS), action="append",
                    help="restrict to these arms (default: all per clarity)")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--experiments-dir", default="evals/experiments")
    ap.add_argument("--fixtures-dir", default="evals/fixtures")
    ap.add_argument("--run-root", default="")
    ap.add_argument("--out", default="docs/experiments/agentic-workflow-evidence/data/tdd-pays.jsonl")
    ap.add_argument("--only", default="", help="comma-separated experiment stems")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--ship-home-template", default="",
                    help="path whose .claude/ is copied into each 'ship' arm "
                         "cell HOME so the dev-team plugin loads (required when "
                         "the ship arm is included and --skip-dispatch is not set)")
    ap.add_argument("--skip-dispatch", action="store_true")
    ap.add_argument("--no-capture", action="store_true")
    ap.add_argument("--no-review", action="store_true",
                    help="skip the multi-rater review panel at last stage")
    ap.add_argument("--resume", action="store_true",
                    help="skip cells already fully written in --out (4 rows per cell)")
    args = ap.parse_args(argv)

    if not args.skip_dispatch and shutil.which("claude") is None:
        print("error: `claude` CLI not found", file=sys.stderr)
        return 2

    # Build arm-clarity pairs for this run
    pairs = CLARITY_PAIRS.get(args.clarity, CLARITY_PAIRS["both"])
    if args.arm:
        pairs = [(a, c) for (a, c) in pairs if a in args.arm]
    if not pairs:
        print("error: no (arm, clarity) pairs selected", file=sys.stderr)
        return 2

    # Validate ship arm requirements
    ship_template: Path | None = None
    if any(a == "ship" for a, _ in pairs) and not args.skip_dispatch:
        if not args.ship_home_template:
            print(
                "error: the 'ship' arm requires --ship-home-template pointing at a "
                "dir containing a plugin-enabled .claude/ (built once with "
                "`cp -r ~/.claude/plugins $TPL/.claude/`)",
                file=sys.stderr,
            )
            return 2
        ship_template = Path(args.ship_home_template)
        if not (ship_template / ".claude").is_dir():
            print(
                f"error: --ship-home-template {ship_template} has no .claude/ dir",
                file=sys.stderr,
            )
            return 2

    exp_dir = Path(args.experiments_dir)
    fixtures_dir = Path(args.fixtures_dir)
    if not exp_dir.is_dir():
        print(f"error: experiments dir not found: {exp_dir}", file=sys.stderr)
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    experiments = load_experiments(exp_dir, only)
    if not experiments:
        print("error: no exp-tdd-pays-*.json fixtures found", file=sys.stderr)
        return 2

    run_root = (Path(args.run_root) if args.run_root
                else Path(tempfile.mkdtemp(prefix="tdd-pays-run-")))
    run_root.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_cells = len(experiments) * len(pairs) * args.trials
    print(f"experiment: {len(experiments)} tasks × {len(pairs)} arm-clarity pairs "
          f"× {args.trials} trials = {total_cells} cells", file=sys.stderr)
    print(f"arms: {sorted({a for a,_ in pairs})}", file=sys.stderr)
    print(f"model: {args.model}", file=sys.stderr)

    # Build set of already-written (task, arm, clarity, trial, stage) tuples.
    # Per-stage tracking lets --resume skip individual stages, not just full cells,
    # so interrupted runs (process killed mid-cell) resume from the next stage.
    done_stages: set = set()
    done_cells: set = set()
    if args.resume and out_path.exists():
        from collections import Counter
        cell_counts: Counter = Counter()
        with out_path.open() as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _r = json.loads(_line)
                    key = (_r["task"], _r["arm"], _r["clarity"], _r["trial"])
                    done_stages.add(key + (_r["stage"],))
                    cell_counts[key] += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        done_cells = {k for k, v in cell_counts.items() if v >= 4}
        skipped = len(done_cells)
        partial = len({k for k in cell_counts if k not in done_cells})
        if skipped or partial:
            print(f"resume: {skipped} complete cells, {partial} partially-done cells",
                  file=sys.stderr)

    rows_written = 0
    with out_path.open("a") as fh:
        for stem, espec in experiments:
            fixture_dir = fixtures_dir / stem
            chain = espec.get("changeChain", [])
            for arm, clarity in pairs:
                plugin_tpl = ship_template if arm in PLUGIN_ARMS else None
                for trial in range(1, args.trials + 1):
                    cell_key = (stem, arm, clarity, trial)
                    if cell_key in done_cells:
                        print(f"· {stem} :: {arm}/{clarity} :: trial {trial} (skip)",
                              file=sys.stderr)
                        continue
                    print(f"· {stem} :: {arm}/{clarity} :: trial {trial}"
                          f"{' (no-dispatch)' if args.skip_dispatch else ''}",
                          file=sys.stderr)

                    # ── stage0 ──────────────────────────────────────────────
                    # Always re-run stage0 even if its row is already written: the
                    # workdir it produces is needed to seed the change chain below.
                    workdir0 = None
                    prior_sha = None
                    stage0_row, workdir0 = run_stage0(
                        stem, arm, clarity, trial, espec, fixture_dir, run_root,
                        args.model, args.skip_dispatch, not args.no_capture,
                        plugin_template=plugin_tpl)
                    prior_sha = stage0_row.pop("_post_build_sha", None)
                    prod_paths = stage0_row.pop("_prod_paths", [])
                    test_paths = stage0_row.pop("_test_paths", [])
                    stage0_row.pop("_worktree", None)
                    if cell_key + ("stage0",) not in done_stages:
                        fh.write(json.dumps(stage0_row) + "\n")
                        fh.flush()
                        rows_written += 1

                    # ── change chain ─────────────────────────────────────────
                    current_workdir = workdir0
                    try:
                        for i, chain_spec in enumerate(chain):
                            stage_name = f"change{i + 1}"
                            is_last = (i == len(chain) - 1)
                            change_row, new_workdir, new_sha = run_change_stage(
                                stem, arm, clarity, trial, i, chain_spec,
                                espec, fixture_dir, run_root, args.model,
                                args.skip_dispatch, not args.no_capture,
                                seed_worktree=current_workdir, prior_sha=prior_sha,
                                is_last=is_last, do_review=not args.no_review,
                                plugin_template=plugin_tpl)
                            if current_workdir != workdir0:
                                shutil.rmtree(current_workdir, ignore_errors=True)
                            current_workdir = new_workdir
                            prior_sha = new_sha
                            if cell_key + (stage_name,) not in done_stages:
                                fh.write(json.dumps(change_row) + "\n")
                                fh.flush()
                                rows_written += 1
                    finally:
                        shutil.rmtree(current_workdir, ignore_errors=True)
                        if workdir0 is not None and workdir0.exists():
                            shutil.rmtree(workdir0, ignore_errors=True)

    print(f"done: {rows_written} rows → {out_path}", file=sys.stderr)
    print(f"run root: {run_root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
