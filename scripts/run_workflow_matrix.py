#!/usr/bin/env python3
"""One-command runner for the workflow-matrix experiment (prompt 05).

Runs the 7 matrix arms x 4 tasks x base trials, then *sequentially extends*
only the arms whose cost-efficiency ranking is still ambiguous — up to a
trial ceiling — instead of paying for uniform trials everywhere. Wraps
run_refactor_experiment.py (it owns dispatch, sensors, the invariant); this
script only orchestrates batches and analyzes the rows between them.

SAFETY: the default action is a DRY PLAN (no dispatch, no spend). You must pass
--go to actually run the campaign. --analyze-only reads an existing out file
and prints the efficiency frontier without dispatching.

Examples:
  python3 scripts/run_workflow_matrix.py                 # dry plan + cost estimate
  python3 scripts/run_workflow_matrix.py --analyze-only  # frontier from existing data
  python3 scripts/run_workflow_matrix.py --go            # run base + sequential extension
"""
import argparse
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "scripts" / "run_refactor_experiment.py"
DEFAULT_OUT = "docs/experiments/agentic-workflow-evidence/data/refactor-workflow-matrix.jsonl"

# ── the 7 cells (prompt 05). no-refactor-* are excluded: refactoring is fixed on. ──
# arm -> (workflow code, human label)
MATRIX = {
    "tdd-refactor":            ("W1", "TDD (test-first, small) x 1 agent"),
    "continuous-single":       ("W2", "code->test small batches x 1 agent"),
    "continuous-split":        ("W2", "code->test small batches x 2 agents"),
    "one-shot-single":         ("W3", "all code->all tests x 1 agent"),
    "one-shot-split":          ("W3", "all code->all tests x 2 agents"),
    "all-tests-first-single":  ("W4", "all tests->all code x 1 agent"),
    "all-tests-first-split":   ("W4", "all tests->all code x 2 agents"),
}
ARMS = list(MATRIX)

# firmed per-cell cost (run-04 actuals; pilot for the W4 arms) — for the dry estimate only.
ARM_COST = {
    "tdd-refactor": 1.57, "continuous-single": 0.99, "continuous-split": 2.81,
    "one-shot-single": 2.01, "one-shot-split": 2.85,
    "all-tests-first-single": 2.50, "all-tests-first-split": 3.77,
}

# quality composite weights (documented + tunable). Two equally-weighted dimensions.
W_TEST = 0.5   # mutation, core/edge pass, coverage
W_MAINT = 0.5  # maintainability index, complexity, changeability (blast)


# ── harness driver ───────────────────────────────────────────────────────────────
def run_harness(arms, trials, out, tasks, model, skip):
    cmd = [sys.executable, str(HARNESS), "--out", out, "--trials", str(trials),
           "--model", model]
    for a in arms:
        cmd += ["--arm", a]
    for t in (tasks or []):
        cmd += ["--task", t]
    if skip:
        cmd += ["--skip-dispatch"]
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


# ── analysis: build cells, score quality, compute cost-efficiency + bootstrap SE ──
def load_cells(out):
    """Group rows into cells keyed by (task, arm, trial); keep only matrix arms."""
    rows = []
    p = Path(out)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    cells = defaultdict(list)
    for r in rows:
        if r.get("arm") in MATRIX:
            cells[(r["task"], r["arm"], r["trial"])].append(r)
    return cells


def _f(x):
    return float(x) if isinstance(x, (int, float)) else None


def cell_features(stage_rows):
    """Reduce one cell's 4 stage rows to raw quality features + total cost."""
    build = next((r for r in stage_rows if r.get("stage") == "build"), None)
    changes = [r for r in stage_rows if str(r.get("stage", "")).startswith("change")]
    cost = sum((r.get("cost") or {}).get("cost_usd") or 0 for r in stage_rows)
    if build is None:
        return None
    mut = _f((build.get("mutation") or {}).get("score"))
    cov = _f((build.get("coverage") or {}).get("percent"))
    core = 1.0 if build.get("core_passed") else (0.0 if build.get("core_passed") is False else None)
    edge = 1.0 if build.get("edge_passed") else (0.0 if build.get("edge_passed") is False else None)
    mi = _f((build.get("radon") or {}).get("avg_mi"))
    cc = _f((build.get("radon") or {}).get("avg_cc"))
    blasts = [(_f((r.get("blast_radius") or {}).get("churned"))) for r in changes]
    blasts = [b for b in blasts if b is not None]
    blast = sum(blasts) / len(blasts) if blasts else None
    return dict(cost=cost, mut=mut, cov=cov, core=core, edge=edge, mi=mi, cc=cc, blast=blast)


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def arm_raw(cells):
    """Per-arm mean of each raw feature + the per-cell cost list (for bootstrap)."""
    per_arm = defaultdict(list)
    for (task, arm, trial), srows in cells.items():
        f = cell_features(srows)
        if f:
            per_arm[arm].append(f)
    out = {}
    for arm, feats in per_arm.items():
        out[arm] = dict(
            n=len(feats),
            cost=_mean([f["cost"] for f in feats]),
            mut=_mean([f["mut"] for f in feats]),
            cov=_mean([f["cov"] for f in feats]),
            core=_mean([f["core"] for f in feats]),
            edge=_mean([f["edge"] for f in feats]),
            mi=_mean([f["mi"] for f in feats]),
            cc=_mean([f["cc"] for f in feats]),
            blast=_mean([f["blast"] for f in feats]),
            feats=feats,
        )
    return out


def _minmax(vals):
    vals = [v for v in vals if v is not None]
    if len(set(vals)) < 2:
        return None
    return min(vals), max(vals)


def quality(raw_arm, bounds):
    """Composite quality in [0,1] from one arm's raw means + cross-arm bounds.

    Bounded metrics used directly; unbounded lower-better metrics (cc, blast)
    min-max normalized across arms then inverted. Missing metrics are skipped.
    """
    def norm_lower(v, key):
        b = bounds.get(key)
        if v is None or b is None:
            return None
        lo, hi = b
        return 1.0 - (v - lo) / (hi - lo) if hi > lo else None

    test_parts = [p for p in (raw_arm["mut"],
                              (raw_arm["cov"] / 100 if raw_arm["cov"] is not None else None),
                              raw_arm["core"], raw_arm["edge"]) if p is not None]
    maint_parts = [p for p in ((raw_arm["mi"] / 100 if raw_arm["mi"] is not None else None),
                               norm_lower(raw_arm["cc"], "cc"),
                               norm_lower(raw_arm["blast"], "blast")) if p is not None]
    if not test_parts or not maint_parts:
        return None
    return W_TEST * (sum(test_parts) / len(test_parts)) + \
        W_MAINT * (sum(maint_parts) / len(maint_parts))


def efficiency_table(raw, seed=7, iters=300):
    """Return arms sorted by cost-efficiency (quality / cost), each with a bootstrap SE."""
    bounds = {"cc": _minmax([a["cc"] for a in raw.values()]),
              "blast": _minmax([a["blast"] for a in raw.values()])}
    rng = random.Random(seed)
    table = []
    for arm, a in raw.items():
        q = quality(a, bounds)
        if q is None or not a["cost"]:
            continue
        eff = q / a["cost"]
        # bootstrap the arm's own cells (holds cross-arm bounds fixed)
        samples = []
        feats = a["feats"]
        for _ in range(iters):
            res = [feats[rng.randrange(len(feats))] for _ in feats]
            ra = dict(a)
            for k in ("cost", "mut", "cov", "core", "edge", "mi", "cc", "blast"):
                ra[k] = _mean([f[k] for f in res])
            qb = quality(ra, bounds)
            if qb is not None and ra["cost"]:
                samples.append(qb / ra["cost"])
        se = (sum((s - eff) ** 2 for s in samples) / len(samples)) ** 0.5 if samples else 0.0
        table.append(dict(arm=arm, n=a["n"], cost=a["cost"], quality=q, eff=eff, se=se))
    table.sort(key=lambda r: r["eff"], reverse=True)
    return table


def ambiguous(table, k=1.0):
    """Arms whose eff +/- k*SE band overlaps an adjacent arm's band — rank not yet resolved."""
    amb = set()
    for i, r in enumerate(table):
        lo, hi = r["eff"] - k * r["se"], r["eff"] + k * r["se"]
        for j in (i - 1, i + 1):
            if 0 <= j < len(table):
                o = table[j]
                if not (hi < o["eff"] - k * o["se"] or lo > o["eff"] + k * o["se"]):
                    amb.add(r["arm"])
    return amb


def print_frontier(table):
    if not table:
        print("  (no analyzable cells yet)")
        return
    print(f"  {'arm':24} {'wf':3} {'n':>3} {'cost$':>6} {'quality':>7} {'qual/$':>7} {'SE':>6}")
    for r in table:
        wf = MATRIX[r["arm"]][0]
        print(f"  {r['arm']:24} {wf:3} {r['n']:3d} {r['cost']:6.2f} "
              f"{r['quality']:7.3f} {r['eff']:7.3f} {r['se']:6.3f}")


# ── orchestration ────────────────────────────────────────────────────────────────
def dry_plan(args):
    print("WORKFLOW-MATRIX CAMPAIGN — DRY PLAN (no dispatch; pass --go to run)\n")
    tasks = args.task or ["fare", "payroll", "cart", "grades"]
    print(f"arms ({len(ARMS)}): " + ", ".join(ARMS))
    print(f"tasks ({len(tasks)}): " + ", ".join(tasks))
    print(f"base trials/cell: {args.base_trials}   extend batch: {args.extend_batch}   "
          f"ceiling: {args.max_trials}")
    print(f"model: {args.model}   out: {args.out}\n")
    per_col = sum(ARM_COST[a] for a in ARMS)
    base = per_col * len(tasks) * args.base_trials
    ceil = per_col * len(tasks) * args.max_trials
    print(f"per task x trial (7 arms): ~${per_col:.2f}")
    print(f"base campaign  ({args.base_trials} trials x {len(tasks)} tasks x 7 arms = "
          f"{args.base_trials*len(tasks)*7} cells): ~${base:.0f}")
    print(f"if every arm extends to the {args.max_trials}-trial ceiling: ~${ceil:.0f} (upper bound)")
    print("\nSequential extension: after the base batch, only arms whose qual/$ rank is still")
    print(f"ambiguous (CI overlaps a neighbor) get +{args.extend_batch} trials, up to the ceiling.")
    print("Expected spend lands between the two figures above.\n")
    print("Run for real with:  python3 scripts/run_workflow_matrix.py --go")


def campaign(args):
    tasks = args.task or None
    print(f"=== base campaign: {args.base_trials} trials, {len(ARMS)} arms ===")
    if run_harness(ARMS, args.base_trials, args.out, tasks, args.model, args.skip_dispatch):
        print("harness returned non-zero on base batch; stopping.")
        return 1
    trials_at = {a: args.base_trials for a in ARMS}
    rnd = 0
    while True:
        rnd += 1
        table = efficiency_table(arm_raw(load_cells(args.out)))
        print(f"\n=== frontier after round {rnd} ===")
        print_frontier(table)
        amb = {a for a in ambiguous(table) if trials_at[a] < args.max_trials}
        if not amb:
            print("\nNo ambiguous arms below the ceiling — campaign complete.")
            break
        print(f"\nExtending ambiguous arms: {', '.join(sorted(amb))}")
        for arm in sorted(amb):
            target = min(args.max_trials, trials_at[arm] + args.extend_batch)
            if run_harness([arm], target, args.out, tasks, args.model, args.skip_dispatch):
                print(f"harness non-zero extending {arm}; stopping.")
                return 1
            trials_at[arm] = target
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description="Workflow-matrix campaign runner (prompt 05).")
    ap.add_argument("--go", action="store_true", help="actually dispatch (default: dry plan)")
    ap.add_argument("--analyze-only", action="store_true",
                    help="print the efficiency frontier from an existing out file; no dispatch")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--task", action="append", help="task(s); default all four")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--base-trials", type=int, default=6)
    ap.add_argument("--extend-batch", type=int, default=3)
    ap.add_argument("--max-trials", type=int, default=12)
    ap.add_argument("--skip-dispatch", action="store_true",
                    help="pass-through harness self-test (runs the pipeline with no model calls)")
    args = ap.parse_args(argv)

    if args.analyze_only:
        print(f"=== efficiency frontier from {args.out} ===")
        print_frontier(efficiency_table(arm_raw(load_cells(args.out))))
        return 0
    if not args.go:
        dry_plan(args)
        return 0
    return campaign(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
