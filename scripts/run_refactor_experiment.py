#!/usr/bin/env python3
"""Clean-room runner for the refactor-granularity experiment (RQ-F).

Tests EXACTLY the prompt's factors and no more:
  - granularity:  one-shot vs continuous refactoring
  - protection:   tests free vs frozen during the refactor
  - authorship:   single agent vs split (independent coder + tester)
  - plus the tdd-refactor reference arm
Clear specs only. No spec-plan-build arm. No reuse of prior scripts or data.

Each cell (task x arm x trial) runs build (stage0) + a 3-change chain, fully
isolated in its own worktree and scratch HOME. One JSONL row per cell-stage.

Sensors (all defensive — a failure yields nulls, never a crashed cell):
  changeability: blast radius (git numstat across a change)
  modularity:    radon (cc, mi) + lizard (ccn, token, params)  [static, no model]
  test quality:  CORE/EDGE/change pass, mutation score, branch coverage, smells
  process:       refactor granularity (count of refactor: commits),
                 test-LOC churn during refactor (doubles as frozen compliance)
  cost:          cost_usd / tokens / turns from the dispatch JSON

Usage:
  python3 scripts/run_refactor_experiment.py --skip-dispatch            # free self-test
  python3 scripts/run_refactor_experiment.py --arm test-after-refactor --task fare --trials 1
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

# ── arms: exactly the prompt's factors ──────────────────────────────────────────
PYTEST_RULE = (
    " Write tests as pytest tests in files named test_*.py so they run with "
    "`python -m pytest -q`. Keep production code in the module named in the spec."
)
COMMIT_RULE = (
    " Mark your workflow with git commits: commit with a message starting 'green:' "
    "every time your whole test suite passes, and a message starting 'refactor:' "
    "for each refactoring step (restructuring with the tests staying green). Always "
    "make a 'green:' commit before any 'refactor:' commit."
)
FROZEN_RULE = (
    " FROZEN TESTS: during any 'refactor:' step you must NOT add, edit, or delete "
    "any test_*.py file. Restructure production code only; the tests from your last "
    "'green:' commit must still pass unchanged."
)

# granularity, protection, authorship per arm
ARMS = {
    "tdd-refactor": dict(granularity="continuous", protection="frozen",
                         authorship="single", reference=True),
    "test-after-refactor": dict(granularity="one-shot", protection="free",
                                authorship="single"),
    "test-after-refactor-frozen": dict(granularity="one-shot", protection="frozen",
                                       authorship="single"),
    "test-after-continuous": dict(granularity="continuous", protection="free",
                                  authorship="single"),
    "test-after-continuous-frozen": dict(granularity="continuous", protection="frozen",
                                         authorship="single"),
    # split-authorship variants reuse the same granularity/protection cells
    "test-after-refactor-split": dict(granularity="one-shot", protection="free",
                                      authorship="split"),
    "test-after-refactor-frozen-split": dict(granularity="one-shot", protection="frozen",
                                             authorship="split"),
    "test-after-continuous-split": dict(granularity="continuous", protection="free",
                                        authorship="split"),
    "test-after-continuous-frozen-split": dict(granularity="continuous", protection="frozen",
                                               authorship="split"),
}


def build_prompt(arm: str, spec: str) -> str:
    a = ARMS[arm]
    if arm == "tdd-refactor":
        body = (f"Implement the spec in {spec} using strict TDD: for each behavior, "
                "write a failing test (RED), the minimum code to pass (GREEN), then "
                "REFACTOR before moving on. Make the acceptance behavior correct.")
    else:
        gran = ("After EACH increment is green, immediately refactor it before moving "
                "on (refactor continuously, in small steps)."
                if a["granularity"] == "continuous" else
                "Build the whole feature to green first, then do a SINGLE refactoring "
                "pass at the end.")
        body = (f"Implement the spec in {spec}. Write all production code first, then a "
                f"test suite covering the behavior. {gran} Make the acceptance behavior "
                "correct.")
    rule = body + PYTEST_RULE + COMMIT_RULE
    if a["protection"] == "frozen":
        rule += FROZEN_RULE
    return rule


def split_coder_prompt(spec: str, arm: str) -> str:
    gran = ("Refactor continuously as you go, in small steps."
            if ARMS[arm]["granularity"] == "continuous" else
            "Get it working first; a separate refactor pass comes later.")
    return (f"Implement ONLY the production code for the spec in {spec}, in the module "
            f"it names. Do NOT write any tests — a separate engineer writes the tests. "
            f"Make the behavior correct. {gran}" + COMMIT_RULE)


def tester_prompt(spec: str) -> str:
    return (f"Production code implementing {spec} already exists in this directory. "
            "Write a thorough pytest suite (files named test_*.py) covering the spec's "
            "behavior, including edge and boundary cases. Do NOT modify the production "
            "code." + COMMIT_RULE)


def split_refactor_prompt(spec: str, arm: str) -> str:
    """Phase 3 of the split build: the coder refactors with the tester's suite present.

    This is where the protection factor bites for split authorship — there is now a
    real, independently-authored test suite to either freeze or let churn.
    """
    a = ARMS[arm]
    scope = ("Do a single, thorough refactoring pass over the production code."
             if a["granularity"] == "one-shot" else
             "Do a light final refactoring pass over the production code.")
    base = (f"The production code for {spec} and an independent pytest suite both exist "
            f"in this directory. {scope} Improve the structure of the production code "
            "without changing its behavior; the suite must stay green. Commit each step "
            "with a message starting 'refactor:'.")
    if a["protection"] == "frozen":
        base += (" FROZEN TESTS: you must NOT add, edit, or delete any test_*.py file — "
                 "restructure production code only.")
    else:
        base += (" You MAY update the test files if the refactor changes an interface.")
    return base


def change_prompt(arm: str, change: str) -> str:
    a = ARMS[arm]
    base = (f"This is an existing, working feature. Apply the change in {change}, keeping "
            "the existing test suite green as your safety net.")
    if arm == "tdd-refactor":
        base = (f"This is an existing feature. Apply the change in {change} with strict "
                "TDD (RED-GREEN-REFACTOR), keeping the existing suite green.")
    rule = base + PYTEST_RULE + COMMIT_RULE
    if a["protection"] == "frozen":
        rule += FROZEN_RULE
    return rule


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


def run_build(task, arm, trial, model, fixture_dir, run_root, skip):
    cell = f"{task['name']}__{arm}__t{trial}__build"
    home = run_root / "homes" / cell
    home.mkdir(parents=True, exist_ok=True)
    env = cell_env(home)
    workdir = Path(tempfile.mkdtemp(prefix=f"rg-{cell}-"))
    shutil.copytree(fixture_dir / task["golden"], workdir, dirs_exist_ok=True)
    base = git_init_commit(workdir)
    spec = task["spec"]
    shutil.copy2(fixture_dir / spec, workdir / Path(spec).name)
    cost = {"parsed": False}
    if not skip:
        if ARMS[arm]["authorship"] == "split":
            sname = Path(spec).name
            c = dispatch(workdir, split_coder_prompt(sname, arm), model, env,
                         run_root / "raw" / f"{cell}-coder.json")
            commit_all(workdir, "green: coder build")
            t = dispatch(workdir, tester_prompt(sname), model, env,
                         run_root / "raw" / f"{cell}-tester.json")
            commit_all(workdir, "green: tester suite")
            rf = dispatch(workdir, split_refactor_prompt(sname, arm), model, env,
                          run_root / "raw" / f"{cell}-refactor.json")
            parts = [c, t, rf]
            cost = {"cost_usd": sum(p.get("cost_usd") or 0 for p in parts),
                    "num_turns": sum(p.get("num_turns") or 0 for p in parts),
                    "is_error": any(p.get("is_error") for p in parts),
                    "parsed": True, "split": True, "phases": 3}
        else:
            cost = dispatch(workdir, build_prompt(arm, Path(spec).name), model, env,
                            run_root / "raw" / f"{cell}.json")
    commit_all(workdir, "green: build complete")
    prod, tests = prod_files(workdir), test_files(workdir)
    proc = refactor_process(workdir, base)
    row = {
        "ts": _utc(), "task": task["name"], "arm": arm, "trial": trial,
        "stage": "build", "model": model, **ARMS[arm],
        "core_passed": grade(workdir, env, fixture_dir, task["coreFiles"]) if prod else None,
        "edge_passed": grade(workdir, env, fixture_dir, task["edgeFiles"]) if prod else None,
        "cost": cost, "process": proc,
        "radon": measure_radon(workdir, prod), "lizard": measure_lizard(workdir, prod),
        "smells": measure_smells(workdir, tests),
        "coverage": measure_coverage(workdir, env, prod),
        "mutation": measure_mutation(workdir, env, prod, tests),
        "frozen_violation": (ARMS[arm]["protection"] == "frozen"
                             and proc["test_loc_churn_in_refactor"] > 0),
    }
    return row, workdir, base


def run_change(task, arm, trial, model, fixture_dir, run_root, idx, change_spec,
               acc_so_far, workdir, prior_sha, skip):
    cell = f"{task['name']}__{arm}__t{trial}__change{idx}"
    home = run_root / "homes" / cell
    home.mkdir(parents=True, exist_ok=True)
    env = cell_env(home)
    spec = change_spec["spec"]
    shutil.copy2(fixture_dir / spec, workdir / Path(spec).name)
    cost = {"parsed": False}
    if not skip:
        cost = dispatch(workdir, change_prompt(arm, Path(spec).name), model, env,
                        run_root / "raw" / f"{cell}.json")
    commit_all(workdir, f"green: change{idx} complete")
    prod, tests = prod_files(workdir), test_files(workdir)
    blast = measure_blast(workdir, prior_sha)
    passed = grade(workdir, env, fixture_dir, acc_so_far) if prod else None
    row = {
        "ts": _utc(), "task": task["name"], "arm": arm, "trial": trial,
        "stage": f"change{idx}", "model": model, **ARMS[arm],
        "passed": passed, "blast_radius": blast, "cost": cost,
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
