#!/usr/bin/env python3
"""Clean-room runner for the refactoring-cadence experiment (granularity x authorship).

Factors (and nothing more):
  - granularity:  none / one-shot / continuous refactoring
  - authorship:   single agent vs split (independent coder + tester)
  - plus the tdd-refactor reference arm
INVARIANT (all arms): refactoring never changes the tests. Clear specs only. No
spec-plan-build arm. No reuse of prior scripts or data.

Each cell (task x arm x trial) runs build + a 3-change chain, fully isolated in
its own worktree and scratch HOME. One JSONL row per cell-stage.

Sensors (all defensive — a failure yields nulls, never a crashed cell):
  changeability: blast radius (git numstat across a change)
  modularity:    radon (cc, mi) + lizard (ccn, token, params)  [static, no model]
  test quality:  CORE/EDGE/change pass, mutation score, branch coverage, smells
  process:       refactor count (refactor: commits), attempted test churn during
                 refactor (must be 0 — the tests-frozen invariant check)
  cost:          cost_usd / tokens / turns from the dispatch JSON

Usage:
  python3 scripts/run_refactor_experiment.py --skip-dispatch            # free self-test
  python3 scripts/run_refactor_experiment.py --arm one-shot-single --task fare --trials 1
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "evals" / "refactor-granularity"
PER_MUTANT_TIMEOUT = 30
MAX_MUTANTS = 25

# ── arms: corrected design ───────────────────────────────────────────────
# INVARIANT in every arm: refactoring restructures production code only and leaves
# the tests unchanged. Tests change only to express new behavior (the change chain),
# never during a refactor step. We vary granularity x authorship; ordering is fixed
# to test-after except for the tdd-refactor reference (test-first). Enforcement: a
# separate refactor dispatch has any test-file edits reverted to the pre-refactor
# ("green") snapshot. Inline-refactor arms (continuous, tdd) can't be reverted
# mid-dispatch, so their refactor-commit test churn is recorded as a violation flag.
PYTEST_RULE = (
    " Write tests as pytest tests in files named test_*.py so they run with "
    "`python -m pytest -q`. Keep production code in the module named in the spec."
)
GREEN_RULE = (
    " Each time your whole test suite passes, commit with a message starting 'green:'."
)
REFACTOR_RULE = (
    " When you refactor (restructure without changing behavior), do NOT add, edit, or "
    "delete any test_*.py file — the existing tests must keep passing. Commit refactor "
    "steps with a message starting 'refactor:'."
)

# granularity x authorship (+ ordering); reference arm flagged
ARMS = {
    "tdd-refactor": dict(granularity="continuous", authorship="single",
                         ordering="test-first", reference=True),
    "no-refactor-single": dict(granularity="none", authorship="single",
                               ordering="test-after"),
    "one-shot-single": dict(granularity="one-shot", authorship="single",
                            ordering="test-after"),
    "continuous-single": dict(granularity="continuous", authorship="single",
                              ordering="test-after"),
    "no-refactor-split": dict(granularity="none", authorship="split",
                              ordering="test-after"),
    "one-shot-split": dict(granularity="one-shot", authorship="split",
                           ordering="test-after"),
    "continuous-split": dict(granularity="continuous", authorship="split",
                             ordering="test-after"),
    # W4 (all tests first, then code to pass, refactor after green) — big-batch,
    # test-first. The one-shot mechanism (separate, revertable refactor dispatch)
    # carries the "refactor after each iteration" rule; batch="big" selects the
    # write-all-tests-then-all-code prompt instead of the incremental TDD loop.
    "all-tests-first-single": dict(granularity="one-shot", authorship="single",
                                   ordering="test-first", batch="big"),
    "all-tests-first-split": dict(granularity="one-shot", authorship="split",
                                  ordering="test-first", batch="big"),
}

# Arms whose refactoring is interleaved inside the write dispatch — cannot be
# physically reverted, so the invariant is enforced by instruction + churn detection.
INLINE_REFACTOR = {"tdd-refactor", "continuous-single"}


def write_prompt_single(arm: str, spec: str) -> str:
    a = ARMS[arm]
    if a["ordering"] == "test-first":
        if a.get("batch") == "big":
            return (f"Implement the spec in {spec} test-first in one batch: FIRST write a "
                    "complete pytest suite covering every behavior in the spec, including edge "
                    "and boundary cases (all tests fail — no production code exists yet). THEN "
                    "write the production code until the whole suite passes. Do NOT refactor "
                    "yet — a separate refactoring step follows." + PYTEST_RULE + GREEN_RULE)
        return (f"Implement the spec in {spec} using strict TDD: for each behavior write "
                "a failing test (RED), the minimum code to pass (GREEN), then REFACTOR "
                "the production code before the next behavior. Make the acceptance "
                "behavior correct." + PYTEST_RULE + GREEN_RULE + REFACTOR_RULE)
    body = (f"Implement the spec in {spec}. Write the production code, then a pytest suite "
            "covering the behavior, until all tests pass.")
    if a["granularity"] == "continuous":
        body += (" Build incrementally: after each behavior is green, refactor the "
                 "production code (without changing any test) before the next.")
        return body + PYTEST_RULE + GREEN_RULE + REFACTOR_RULE
    body += (" Do NOT refactor yet — a separate refactoring step follows."
             if a["granularity"] == "one-shot" else " Do not refactor.")
    return body + PYTEST_RULE + GREEN_RULE


def coder_prompt(arm: str, spec: str) -> str:
    extra = (" Refactor the production code continuously as you go."
             if ARMS[arm]["granularity"] == "continuous" else
             " Get it correct; a separate refactoring step may follow.")
    return (f"Implement ONLY the production code for the spec in {spec}, in the module it "
            "names. Do NOT write any tests — a separate engineer writes them." + extra
            + " Commit your work.")


def tester_prompt(spec: str) -> str:
    return (f"Production code implementing {spec} already exists here. Write a thorough "
            "pytest suite (files named test_*.py) covering the spec's behavior, including "
            "edge and boundary cases. Do NOT modify the production code." + GREEN_RULE)


def refactor_prompt(doc: str) -> str:
    return (f"The feature for {doc} is implemented and all tests pass. Refactor the "
            "PRODUCTION code to improve its structure WITHOUT changing behavior. You must "
            "NOT add, edit, or delete any test_*.py file — every existing test must still "
            "pass unchanged. Commit each step with a message starting 'refactor:'.")


def change_write_prompt(arm: str, change: str) -> str:
    a = ARMS[arm]
    if a["ordering"] == "test-first":
        if a.get("batch") == "big":
            return (f"This is an existing, working feature. Apply the change in {change} "
                    "test-first in one batch: FIRST add or update tests covering the new "
                    "behavior (they fail), THEN change the production code until all tests "
                    "pass. Do NOT refactor yet — a separate refactoring step follows."
                    + PYTEST_RULE + GREEN_RULE)
        return (f"This is an existing feature. Apply the change in {change} with strict "
                "TDD: RED for the new behavior, GREEN, then REFACTOR the production code "
                "without changing existing tests." + PYTEST_RULE + GREEN_RULE
                + REFACTOR_RULE)
    base = (f"This is an existing, working feature. Apply the change in {change}. Update "
            "or add tests for the NEW behavior and keep all tests passing.")
    if a["granularity"] == "continuous":
        base += " After it is green, refactor the production code without changing tests."
        return base + PYTEST_RULE + GREEN_RULE + REFACTOR_RULE
    base += (" Do NOT refactor yet — a separate refactoring step follows."
             if a["granularity"] == "one-shot" else " Do not refactor.")
    return base + PYTEST_RULE + GREEN_RULE


def change_coder_prompt(arm: str, change: str) -> str:
    extra = (" Refactor the production code continuously as you go."
             if ARMS[arm]["granularity"] == "continuous" else "")
    return (f"This is an existing feature. Apply the change in {change} to the PRODUCTION "
            "code only; do NOT modify or add tests — a separate engineer updates them."
            + extra + " Commit your work.")


def change_tester_prompt(change: str) -> str:
    return (f"The production code was just changed per {change}. Update or add tests for "
            "the new behavior (test_*.py) and keep all tests passing; do NOT modify the "
            "production code." + GREEN_RULE)


# Test-first split (W4): the tester authors the suite BEFORE any production code,
# then an isolated coder writes production code to make it pass.
def tester_first_prompt(spec: str) -> str:
    return (f"Write a complete pytest suite (files named test_*.py) for the spec in {spec}, "
            "covering all behavior including edge and boundary cases. No production code exists "
            "yet, so the tests will fail — that is expected. Do NOT write any production code; a "
            "separate engineer implements it. Commit your work.")


def coder_topass_prompt(spec: str) -> str:
    return (f"A failing pytest suite for the spec in {spec} already exists. Write ONLY the "
            "production code, in the module the spec names, to make the whole suite pass. Do NOT "
            "add, edit, or delete any test_*.py file." + GREEN_RULE + " Commit your work.")


def change_tester_first_prompt(change: str) -> str:
    return (f"This is an existing, working feature. The change in {change} adds new behavior. "
            "Add or update tests (test_*.py) for the new behavior FIRST — they will fail until "
            "the code is written. Do NOT modify the production code; a separate engineer does.")


def change_coder_topass_prompt(change: str) -> str:
    return (f"This is an existing feature. Tests for the change in {change} were just written and "
            "are failing. Write ONLY the production-code changes to make all tests pass; do NOT "
            "add, edit, or delete any test_*.py file." + GREEN_RULE + " Commit your work.")


# ── shell / git helpers ─────────────────────────────────────────────────────────
def _run(cmd, cwd, env=None, timeout=None):
    return subprocess.run(cmd, cwd=str(cwd), env=env, timeout=timeout,
                          capture_output=True, text=True)


def git(workdir, *args):
    return _run(["git", *args], workdir)


def git_init_commit(workdir):
    git(workdir, "init", "-q")
    git(workdir, "config", "user.email", "exp@local")
    git(workdir, "config", "user.name", "exp")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", "baseline")
    return git(workdir, "rev-parse", "HEAD").stdout.strip()


def head_sha(workdir):
    return git(workdir, "rev-parse", "HEAD").stdout.strip()


def commit_all(workdir, msg):
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", msg, "--allow-empty")
    return head_sha(workdir)


def is_test(p: Path) -> bool:
    return p.name.startswith("test_")


def is_acc(p: Path) -> bool:
    return p.name.startswith("acc_")


def prod_files(workdir: Path):
    return sorted(p for p in workdir.glob("*.py")
                  if not is_test(p) and not is_acc(p))


def test_files(workdir: Path):
    return sorted(workdir.glob("test_*.py"))


# ── dispatch ────────────────────────────────────────────────────────────────────
def cell_env(home: Path):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["IS_SANDBOX"] = "1"
    env["COVERAGE_FILE"] = str(home / ".coverage")
    return env


def _dispatch_once(workdir, prompt, model, env, raw_out):
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json",
           "--dangerously-skip-permissions"]
    out = {"cost_usd": None, "tokens_total": None, "num_turns": None,
           "is_error": None, "parsed": False}
    try:
        r = subprocess.run(cmd, cwd=str(workdir), env=env, capture_output=True,
                           text=True, timeout=900)
    except subprocess.TimeoutExpired:
        out["is_error"] = True
        out["timeout"] = True
        return out
    if raw_out:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(r.stdout[:200000])
    try:
        d = json.loads(r.stdout)
        u = d.get("usage", {})
        out.update(cost_usd=d.get("total_cost_usd"),
                   tokens_total=(u.get("input_tokens", 0) + u.get("output_tokens", 0)
                                 + u.get("cache_creation_input_tokens", 0)
                                 + u.get("cache_read_input_tokens", 0)),
                   num_turns=d.get("num_turns"), is_error=d.get("is_error"),
                   parsed=True)
    except Exception:
        out["is_error"] = True
    return out


def dispatch(workdir, prompt, model, env, raw_out: Path | None):
    """Dispatch with backoff retry — survives transient rate-limit/API errors."""
    last = None
    for attempt, backoff in enumerate((0, 15, 45)):
        if backoff:
            time.sleep(backoff)
        last = _dispatch_once(workdir, prompt, model, env, raw_out)
        if last.get("parsed") and not last.get("is_error"):
            if attempt:
                last["retries"] = attempt
            return last
    last["retries"] = 2
    return last


# ── sensors ─────────────────────────────────────────────────────────────────────
def numstat(workdir, sha_from, sha_to, predicate):
    """Sum added/deleted lines and file count for files matching predicate(name)."""
    r = git(workdir, "diff", "--numstat", sha_from, sha_to)
    add = dele = files = 0
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, name = parts
        if not predicate(Path(name)):
            continue
        files += 1
        add += int(a) if a.isdigit() else 0
        dele += int(d) if d.isdigit() else 0
    return {"lines_added": add, "lines_deleted": dele, "files_changed": files}


def measure_blast(workdir, prior_sha):
    cur = head_sha(workdir)
    prod = numstat(workdir, prior_sha, cur, lambda p: not is_test(p) and not is_acc(p))
    return {**prod, "churned": prod["lines_added"] + prod["lines_deleted"]}


def refactor_process(workdir, baseline_sha):
    """Granularity (# refactor: commits) and test-LOC churn during refactors.

    Test churn doubles as the frozen-compliance check: >0 churn under a frozen
    arm is a violation.
    """
    r = git(workdir, "log", "--reverse", "--format=%H%x09%s", f"{baseline_sha}..HEAD")
    commits = [ln.split("\t", 1) for ln in r.stdout.splitlines() if "\t" in ln]
    first_green = next((sha for sha, msg in commits if msg.startswith("green:")), None)
    refactors = [sha for sha, msg in commits if msg.startswith("refactor:")]
    test_churn = 0
    for sha in refactors:
        ts = numstat(workdir, f"{sha}~1", sha, is_test)
        test_churn += ts["lines_added"] + ts["lines_deleted"]
    return {"granularity": len(refactors), "first_green": first_green,
            "test_loc_churn_in_refactor": test_churn, "commits": len(commits)}


def measure_radon(workdir, prod):
    if not prod or not shutil.which("radon"):
        return {"avg_cc": None, "avg_mi": None}
    ccs, mis = [], []
    for p in prod:
        r = _run(["radon", "cc", "-s", "-a", str(p)], workdir)
        m = re.search(r"Average complexity:\s+\w+\s+\(([0-9.]+)\)", r.stdout)
        if m:
            ccs.append(float(m.group(1)))
        r2 = _run(["radon", "mi", "-s", str(p)], workdir)
        m2 = re.search(r"-\s+\w+\s+\(([0-9.]+)\)", r2.stdout)
        if m2:
            mis.append(float(m2.group(1)))
    return {"avg_cc": round(sum(ccs) / len(ccs), 2) if ccs else None,
            "avg_mi": round(sum(mis) / len(mis), 2) if mis else None}


def measure_lizard(workdir, prod):
    if not prod or not shutil.which("lizard"):
        return {"avg_ccn": None, "avg_token": None, "max_params": None, "nloc": None}
    r = _run(["lizard", *[str(p) for p in prod]], workdir)
    # parse the summary "Total" line: NLOC Avg.NLOC AvgCCN Avg.token function_cnt
    for line in r.stdout.splitlines():
        nums = re.findall(r"[0-9]+\.?[0-9]*", line)
        if line.strip().startswith(tuple("0123456789")) and len(nums) >= 4 and "Total" not in line:
            pass
    m = re.search(r"^\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\d+\s+file", r.stdout, re.M)
    if not m:
        # fallback: the averages row before "file analyzed"
        rows = [l for l in r.stdout.splitlines() if re.match(r"\s*[\d.]+\s+[\d.]+\s+[\d.]+", l)]
        if rows:
            nums = re.findall(r"[\d.]+", rows[-1])
            if len(nums) >= 4:
                return {"avg_ccn": float(nums[2]), "avg_token": float(nums[3]),
                        "max_params": None, "nloc": float(nums[0])}
        return {"avg_ccn": None, "avg_token": None, "max_params": None, "nloc": None}
    return {"nloc": float(m.group(1)), "avg_ccn": float(m.group(3)),
            "avg_token": float(m.group(4)), "max_params": None}


def measure_smells(workdir, tests):
    asserts = assertless = mocks = sleeps = test_loc = ntests = 0
    for p in tests:
        try:
            src = p.read_text()
            test_loc += len([l for l in src.splitlines() if l.strip()])
            tree = ast.parse(src)
        except Exception:
            continue
        mocks += len(re.findall(r"\b(Mock|patch|MagicMock|monkeypatch)\b", src))
        sleeps += len(re.findall(r"\bsleep\s*\(", src))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                ntests += 1
                na = sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))
                asserts += na
                if na == 0:
                    assertless += 1
    return {"n_tests": ntests, "asserts": asserts, "assertless_tests": assertless,
            "mock_uses": mocks, "sleep_uses": sleeps, "test_loc": test_loc}


def _pytest_green(workdir, env):
    r = _run(["python3", "-m", "pytest", "-q", "-x"], workdir, env, timeout=120)
    return r.returncode == 0


def measure_coverage(workdir, env, prod):
    if not prod:
        return {"percent": None}
    src = ",".join(p.stem for p in prod)
    try:
        _run(["python3", "-m", "coverage", "run", "--branch", f"--source={src}",
              "-m", "pytest", "-q"], workdir, env, timeout=180)
        r = _run(["python3", "-m", "coverage", "json", "-o", "-"], workdir, env, timeout=60)
        d = json.loads(r.stdout)
        return {"percent": round(d["totals"]["percent_covered"], 1)}
    except Exception:
        return {"percent": None}


_MUT = [(ast.Add, ast.Sub), (ast.Sub, ast.Add), (ast.Mult, ast.Add),
        (ast.Lt, ast.LtE), (ast.LtE, ast.Lt), (ast.Gt, ast.GtE), (ast.GtE, ast.Gt),
        (ast.Eq, ast.NotEq), (ast.NotEq, ast.Eq)]


def _mutants(src):
    """Yield mutated sources by swapping one operator at a time."""
    try:
        tree = ast.parse(src)
    except Exception:
        return
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, (ast.BinOp, ast.Compare))]
    out = []
    for idx, node in enumerate(nodes):
        if isinstance(node, ast.BinOp):
            op = node.op
            for a, b in _MUT:
                if isinstance(op, a):
                    node.op = b()
                    try:
                        out.append(ast.unparse(ast.fix_missing_locations(tree)))
                    except Exception:
                        pass
                    node.op = op
                    break
        else:  # Compare
            ops = node.ops
            for i, op in enumerate(ops):
                for a, b in _MUT:
                    if isinstance(op, a):
                        ops[i] = b()
                        try:
                            out.append(ast.unparse(ast.fix_missing_locations(tree)))
                        except Exception:
                            pass
                        ops[i] = op
                        break
    return out


def measure_mutation(workdir, env, prod, tests):
    if not prod or not tests:
        return {"score": None, "killed": 0, "total": 0}
    if not _pytest_green(workdir, env):
        return {"score": None, "killed": 0, "total": 0, "baseline_green": False}
    killed = total = 0
    for p in prod:
        orig = p.read_text()
        muts = _mutants(orig) or []
        for src in muts[:MAX_MUTANTS]:
            if src == orig:
                continue
            total += 1
            p.write_text(src)
            try:
                r = _run(["python3", "-m", "pytest", "-q", "-x"], workdir, env,
                         timeout=PER_MUTANT_TIMEOUT)
                if r.returncode != 0:
                    killed += 1
            except subprocess.TimeoutExpired:
                killed += 1
            finally:
                p.write_text(orig)
    return {"score": round(killed / total, 3) if total else None,
            "killed": killed, "total": total, "baseline_green": True}


def grade(workdir, env, fixture_dir, acc_files):
    """Inject hidden acceptance files, run them, return pass bool. Cleans up."""
    injected = []
    for name in acc_files:
        src = fixture_dir / name
        if src.exists():
            shutil.copy2(src, workdir / name)
            injected.append(workdir / name)
    cmds = [["python3", "-m", "pytest", *[i.name for i in injected], "-q", "--tb=line"]]
    ok = True
    for c in cmds:
        r = _run(c, workdir, env, timeout=120)
        ok = ok and r.returncode == 0
    for i in injected:
        i.unlink(missing_ok=True)
    return ok and bool(injected)


# ── stage execution ─────────────────────────────────────────────────────────────
def _utc():
    return datetime.now(timezone.utc).isoformat()


def enforce_refactor(workdir, green_sha):
    """Enforce the invariant after a separate refactor dispatch.

    Revert any test-file change the refactor made back to the green snapshot (a true
    refactor changes no behavior, so reverting is a no-op; a refactor that altered an
    interface will now fail grading — correctly caught). Returns the attempted test
    churn (lines the refactor tried to change in tests) for reporting.
    """
    attempted = numstat(workdir, green_sha, head_sha(workdir), is_test)
    churn = attempted["lines_added"] + attempted["lines_deleted"]
    r = git(workdir, "ls-tree", "-r", "--name-only", green_sha)
    green_tests = [n for n in r.stdout.split() if Path(n).name.startswith("test_")]
    if green_tests:
        git(workdir, "checkout", green_sha, "--", *green_tests)
    keep = {Path(g).name for g in green_tests}
    for t in test_files(workdir):
        if t.name not in keep:
            t.unlink()
    commit_all(workdir, "chore: revert test edits to green (invariant)")
    return churn


def _cost(parts):
    return {"cost_usd": sum(p.get("cost_usd") or 0 for p in parts),
            "num_turns": sum(p.get("num_turns") or 0 for p in parts),
            "is_error": any(p.get("is_error") for p in parts),
            "parsed": True, "phases": len(parts)}


def _do_stage(workdir, arm, doc, model, env, run_root, cell, change):
    """Run one stage's dispatches per arm; return (cost, attempted_test_churn)."""
    a = ARMS[arm]
    parts = []
    attempted = None
    raw = lambda suffix="": run_root / "raw" / f"{cell}{suffix}.json"
    if a["authorship"] == "single":
        wp = change_write_prompt(arm, doc) if change else write_prompt_single(arm, doc)
        parts.append(dispatch(workdir, wp, model, env, raw()))
        green = commit_all(workdir, "green: write")
        if a["granularity"] == "one-shot":
            parts.append(dispatch(workdir, refactor_prompt(doc), model, env,
                                  raw("-refactor")))
            attempted = enforce_refactor(workdir, green)
    elif a["ordering"] == "test-first":  # split, test-first (W4): tests authored first
        tp = change_tester_first_prompt(doc) if change else tester_first_prompt(doc)
        parts.append(dispatch(workdir, tp, model, env, raw("-tester")))
        commit_all(workdir, "checkpoint: tests-first (red)")
        cp = change_coder_topass_prompt(doc) if change else coder_topass_prompt(doc)
        parts.append(dispatch(workdir, cp, model, env, raw("-coder")))
        green = commit_all(workdir, "green: coder")
        if a["granularity"] in ("one-shot", "continuous"):
            parts.append(dispatch(workdir, refactor_prompt(doc), model, env,
                                  raw("-refactor")))
            attempted = enforce_refactor(workdir, green)
    else:  # split authorship, test-after
        cp = change_coder_prompt(arm, doc) if change else coder_prompt(arm, doc)
        tp = change_tester_prompt(doc) if change else tester_prompt(doc)
        parts.append(dispatch(workdir, cp, model, env, raw("-coder")))
        commit_all(workdir, "green: coder")
        parts.append(dispatch(workdir, tp, model, env, raw("-tester")))
        green = commit_all(workdir, "green: tester")
        if a["granularity"] in ("one-shot", "continuous"):
            parts.append(dispatch(workdir, refactor_prompt(doc), model, env,
                                  raw("-refactor")))
            attempted = enforce_refactor(workdir, green)
    return _cost(parts), attempted


def run_build(task, arm, trial, model, fixture_dir, run_root, skip):
    cell = f"{task['name']}__{arm}__t{trial}__build"
    home = run_root / "homes" / cell
    home.mkdir(parents=True, exist_ok=True)
    env = cell_env(home)
    workdir = Path(tempfile.mkdtemp(prefix=f"rg-{cell}-"))
    shutil.copytree(fixture_dir / task["golden"], workdir, dirs_exist_ok=True)
    base = git_init_commit(workdir)
    spec = Path(task["spec"]).name
    shutil.copy2(fixture_dir / task["spec"], workdir / spec)
    cost, attempted = {"parsed": False}, None
    if not skip:
        cost, attempted = _do_stage(workdir, arm, spec, model, env, run_root, cell, False)
    commit_all(workdir, "green: build complete")
    prod, tests = prod_files(workdir), test_files(workdir)
    proc = refactor_process(workdir, base)
    violation = (arm in INLINE_REFACTOR and proc.get("test_loc_churn_in_refactor", 0) > 0)
    row = {
        "ts": _utc(), "task": task["name"], "arm": arm, "trial": trial,
        "stage": "build", "model": model, **ARMS[arm],
        "core_passed": grade(workdir, env, fixture_dir, task["coreFiles"]) if prod else None,
        "edge_passed": grade(workdir, env, fixture_dir, task["edgeFiles"]) if prod else None,
        "cost": cost, "process": proc,
        "refactor_test_churn_attempted": attempted,
        "invariant_violation": violation,
        "radon": measure_radon(workdir, prod), "lizard": measure_lizard(workdir, prod),
        "smells": measure_smells(workdir, tests),
        "coverage": measure_coverage(workdir, env, prod),
        "mutation": measure_mutation(workdir, env, prod, tests),
    }
    return row, workdir, base


def run_change(task, arm, trial, model, fixture_dir, run_root, idx, change_spec,
               acc_so_far, workdir, prior_sha, skip):
    cell = f"{task['name']}__{arm}__t{trial}__change{idx}"
    home = run_root / "homes" / cell
    home.mkdir(parents=True, exist_ok=True)
    env = cell_env(home)
    spec = Path(change_spec["spec"]).name
    shutil.copy2(fixture_dir / change_spec["spec"], workdir / spec)
    cost, attempted = {"parsed": False}, None
    if not skip:
        cost, attempted = _do_stage(workdir, arm, spec, model, env, run_root, cell, True)
    commit_all(workdir, f"green: change{idx} complete")
    prod, tests = prod_files(workdir), test_files(workdir)
    blast = measure_blast(workdir, prior_sha)
    proc = refactor_process(workdir, prior_sha)
    violation = (arm in INLINE_REFACTOR and proc.get("test_loc_churn_in_refactor", 0) > 0)
    passed = grade(workdir, env, fixture_dir, acc_so_far) if prod else None
    row = {
        "ts": _utc(), "task": task["name"], "arm": arm, "trial": trial,
        "stage": f"change{idx}", "model": model, **ARMS[arm],
        "passed": passed, "blast_radius": blast, "cost": cost,
        "refactor_test_churn_attempted": attempted, "invariant_violation": violation,
        "radon": measure_radon(workdir, prod), "smells": measure_smells(workdir, tests),
    }
    return row, head_sha(workdir)


def run_cell(task, arm, trial, model, fixture_dir, run_root, skip):
    rows = []
    build_row, workdir, base = run_build(task, arm, trial, model, fixture_dir,
                                         run_root, skip)
    rows.append(build_row)
    try:
        prior = head_sha(workdir)
        acc = list(task["coreFiles"]) + list(task["edgeFiles"])
        for i, ch in enumerate(task["changeChain"], 1):
            acc = acc + list(ch["accFiles"])
            crow, prior = run_change(task, arm, trial, model, fixture_dir, run_root,
                                     i, ch, acc, workdir, prior, skip)
            rows.append(crow)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", action="append", help="task name(s); default all")
    ap.add_argument("--arm", action="append", choices=list(ARMS),
                    help="arm(s); default all")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--out", default="docs/experiments/data/refactor-granularity.jsonl")
    ap.add_argument("--run-root", default="")
    ap.add_argument("--skip-dispatch", action="store_true",
                    help="run the full pipeline with NO model calls (free self-test)")
    args = ap.parse_args(argv)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    tasks = manifest["tasks"]
    if args.task:
        tasks = [t for t in tasks if t["name"] in args.task]
    arms = args.arm or list(ARMS)
    run_root = Path(args.run_root) if args.run_root else Path(
        tempfile.mkdtemp(prefix="rg-run-"))
    run_root.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resume: a cell is complete when its change3 row already exists in the out file.
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("stage") == "change3":
                done.add((r["task"], r["arm"], r["trial"]))

    n = len(tasks) * len(arms) * args.trials
    print(f"refactor-granularity: {len(tasks)} task(s) x {len(arms)} arm(s) x "
          f"{args.trials} trial(s) = {n} cells; {len(done)} already done; "
          f"run_root={run_root}", flush=True)
    written = skipped = 0
    with out.open("a") as fh:
        for task in tasks:
            fixture_dir = CORPUS / task["dir"]
            for arm in arms:
                for trial in range(1, args.trials + 1):
                    if (task["name"], arm, trial) in done:
                        skipped += 1
                        continue
                    rows = run_cell(task, arm, trial, args.model, fixture_dir,
                                    run_root, args.skip_dispatch)
                    for row in rows:
                        fh.write(json.dumps(row) + "\n")
                        fh.flush()
                        written += 1
                    print(f"  done {task['name']}/{arm}/t{trial} "
                          f"({len(rows)} rows)", flush=True)
    print(f"wrote {written} rows ({skipped} cells skipped) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
