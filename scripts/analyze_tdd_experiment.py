#!/usr/bin/env python3
"""Analyze run_tdd_experiment.py JSONL into the per-size 3x3 (size x arm) grid.

The unit of inference is the TASK: per (task, arm) take the median across trials
of the two-stage total cost (build + change), then form PAIRED arm differences
ACROSS TASKS within a size and test them with an exact sign test and an exact
Wilcoxon signed-rank test (n is small; no SciPy dependency).

Reads one or more JSONL files (the harness writes one row per cell-stage),
dedupes by (task, arm, trial, stage) keeping the LAST occurrence, and prints a
Markdown report fragment plus a machine-readable JSON summary.

Usage:
  python3 scripts/analyze_tdd_experiment.py --data a.jsonl --data b.jsonl \
      [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from itertools import combinations
from pathlib import Path

# Canonical size membership. A task counts toward a size only if it appears here.
SIZES = {
    "small": ["exp-tdd-word-tally", "exp-tdd-roman", "exp-tdd-fizzbuzz",
              "exp-tdd-rpn", "exp-tdd-rle", "exp-tdd-caesar"],
    "medium": ["exp-tdd-stats", "exp-tdd-intervals", "exp-tdd-timeparse",
               "exp-tdd-money", "exp-tdd-matrix", "exp-tdd-csvlite"],
    "large": ["exp-tdd-spreadsheet", "exp-tdd-jsonptr", "exp-tdd-scheduler",
              "exp-tdd-template-engine", "exp-tdd-ledger", "exp-tdd-router"],
}
TASK_SIZE = {t: s for s, ts in SIZES.items() for t in ts}
ARMS = ["build-pipeline", "test-first", "test-after"]


def load(paths: list[Path]) -> dict:
    """Return rows keyed by (task, arm, trial, stage), last-wins."""
    rows: dict[tuple, dict] = {}
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text().strip()
        if not text:
            continue
        # Accept either JSONL (one row per line) or a single JSON array.
        if text[0] == "[":
            items = json.loads(text)
        else:
            items = [json.loads(l) for l in text.splitlines() if l.strip()]
        for r in items:
            key = (r["task"], r["arm"], r["trial"], r["stage"])
            rows[key] = r
    return rows


def _cost(r: dict | None) -> float | None:
    if not r:
        return None
    c = (r.get("cost") or {}).get("cost_usd")
    return float(c) if isinstance(c, (int, float)) else None


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def per_task_arm(rows: dict, size: str) -> dict:
    """task -> arm -> {total_cost(median over trials), build_cost, change_cost,
    pass_build, pass_change, n_trials, cov, mut, turns}."""
    tasks = SIZES[size]
    trials = defaultdict(set)
    for (task, arm, trial, stage) in rows:
        if task in tasks:
            trials[(task, arm)].add(trial)
    out: dict = {t: {} for t in tasks}
    for task in tasks:
        for arm in ARMS:
            ts = sorted(trials.get((task, arm), set()))
            if not ts:
                continue
            totals, builds, changes = [], [], []
            pb, pc, covs, muts, turns = [], [], [], [], []
            for tr in ts:
                b = rows.get((task, arm, tr, "build"))
                c = rows.get((task, arm, tr, "change"))
                bc, cc = _cost(b), _cost(c)
                if bc is not None:
                    builds.append(bc)
                if cc is not None:
                    changes.append(cc)
                if bc is not None or cc is not None:
                    totals.append((bc or 0) + (cc or 0))
                if b is not None:
                    pb.append(bool(b.get("passed")))
                    cv = (b.get("self_coverage") or {}).get("percent")
                    mu = (b.get("mutation") or {}).get("score")
                    if cv is not None:
                        covs.append(cv)
                    if mu is not None:
                        muts.append(mu)
                    tn = (b.get("cost") or {}).get("num_turns")
                    if isinstance(tn, int):
                        turns.append(tn)
                if c is not None:
                    pc.append(bool(c.get("passed")))
            out[task][arm] = {
                "total_cost": _median(totals),
                "build_cost": _median(builds),
                "change_cost": _median(changes),
                "pass_build": pb, "pass_change": pc,
                "cov": _median(covs), "mut": _median(muts),
                "turns": _median(turns), "n_trials": len(ts),
            }
    return out


def sign_test(diffs: list[float]) -> dict:
    """Exact two-sided sign test on nonzero paired differences (positive=first
    arm costs MORE)."""
    nz = [d for d in diffs if abs(d) > 1e-9]
    n = len(nz)
    pos = sum(1 for d in nz if d > 0)
    if n == 0:
        return {"n": 0, "pos": 0, "neg": 0, "p": 1.0}
    k = min(pos, n - pos)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return {"n": n, "pos": pos, "neg": n - pos, "p": round(min(1.0, 2 * tail), 4)}


def wilcoxon(diffs: list[float]) -> dict:
    """Exact two-sided Wilcoxon signed-rank for small n (drops zeros)."""
    nz = [d for d in diffs if abs(d) > 1e-9]
    n = len(nz)
    if n == 0:
        return {"n": 0, "W": None, "p": 1.0}
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(nz[order[j + 1]]) - abs(nz[order[i]])) < 1e-9:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_pos = sum(ranks[i] for i in range(n) if nz[i] > 0)
    w_neg = sum(ranks[i] for i in range(n) if nz[i] < 0)
    W = min(w_pos, w_neg)
    # Exact distribution by enumerating all 2^n sign assignments of ranks 1..n.
    if n <= 18:
        from itertools import product
        base = sorted(abs(r) for r in ranks)
        count = 0
        total = 0
        for signs in product((0, 1), repeat=n):
            total += 1
            wp = sum(base[i] for i in range(n) if signs[i])
            if min(wp, sum(base) - wp) <= W + 1e-9:
                count += 1
        p = round(min(1.0, count / total), 4)
    else:
        p = None
    return {"n": n, "W": W, "w_pos": w_pos, "w_neg": w_neg, "p": p}


def pass_rate(flags: list[bool]) -> str:
    flat = [f for f in flags]
    if not flat:
        return "n/a"
    return f"{sum(flat)}/{len(flat)}"


def analyze_size(rows: dict, size: str) -> dict:
    pta = per_task_arm(rows, size)
    present_arms = [a for a in ARMS
                    if any(a in pta[t] for t in SIZES[size])]
    arm_costs = {a: [] for a in present_arms}
    arm_cov = {a: [] for a in present_arms}
    arm_mut = {a: [] for a in present_arms}
    arm_turns = {a: [] for a in present_arms}
    pb = {a: [] for a in present_arms}
    pc = {a: [] for a in present_arms}
    for task in SIZES[size]:
        for a in present_arms:
            d = pta[task].get(a)
            if not d:
                continue
            if d["total_cost"] is not None:
                arm_costs[a].append((task, d["total_cost"]))
            if d["cov"] is not None:
                arm_cov[a].append(d["cov"])
            if d["mut"] is not None:
                arm_mut[a].append(d["mut"])
            if d["turns"] is not None:
                arm_turns[a].append(d["turns"])
            pb[a].extend(d["pass_build"])
            pc[a].extend(d["pass_change"])
    # Paired arm differences across tasks (only tasks where both arms have cost).
    pairs = {}
    for a1, a2 in combinations(present_arms, 2):
        m1 = dict(arm_costs[a1])
        m2 = dict(arm_costs[a2])
        common = [t for t in SIZES[size] if t in m1 and t in m2]
        diffs = [m1[t] - m2[t] for t in common]  # +ve => a1 costs more
        pairs[f"{a1}__vs__{a2}"] = {
            "tasks": common,
            "diffs": [round(d, 4) for d in diffs],
            "median_diff": round(_median(diffs), 4) if diffs else None,
            "a1_higher_in": sum(1 for d in diffs if d > 0),
            "a2_higher_in": sum(1 for d in diffs if d < 0),
            "sign_test": sign_test(diffs),
            "wilcoxon": wilcoxon(diffs),
        }
    return {
        "size": size,
        "arms": present_arms,
        "arm_median_total_cost": {a: (round(_median([c for _, c in arm_costs[a]]), 4)
                                      if arm_costs[a] else None)
                                  for a in present_arms},
        "arm_median_cov": {a: (round(_median(arm_cov[a]), 1) if arm_cov[a] else None)
                           for a in present_arms},
        "arm_median_mut": {a: (round(_median(arm_mut[a]), 3) if arm_mut[a] else None)
                           for a in present_arms},
        "arm_median_turns": {a: (_median(arm_turns[a]) if arm_turns[a] else None)
                             for a in present_arms},
        "pass_build": {a: pass_rate(pb[a]) for a in present_arms},
        "pass_change": {a: pass_rate(pc[a]) for a in present_arms},
        "per_task_cost": {t: {a: (round(pta[t][a]["total_cost"], 4)
                                  if pta[t].get(a) and pta[t][a]["total_cost"] is not None
                                  else None)
                              for a in present_arms}
                          for t in SIZES[size]},
        "pairs": pairs,
        "n_tasks_with_data": sum(1 for t in SIZES[size] if pta[t]),
    }


def fmt_md(summaries: list[dict]) -> str:
    L = []
    for s in summaries:
        L.append(f"### {s['size'].capitalize()} "
                 f"({s['n_tasks_with_data']} tasks with data)\n")
        L.append("| Arm | Correct build | Correct change | "
                 "Median total cost | Cov% | Mutation | Median turns |")
        L.append("|---|---|---|---|---|---|---|")
        for a in s["arms"]:
            L.append(f"| {a} | {s['pass_build'][a]} | {s['pass_change'][a]} | "
                     f"${s['arm_median_total_cost'][a]} | "
                     f"{s['arm_median_cov'][a]} | {s['arm_median_mut'][a]} | "
                     f"{s['arm_median_turns'][a]} |")
        L.append("")
        for name, p in s["pairs"].items():
            a1, a2 = name.split("__vs__")
            L.append(f"- **{a1} vs {a2}** (n={len(p['tasks'])} paired): "
                     f"median Δ=${p['median_diff']} "
                     f"({a1} higher in {p['a1_higher_in']}, "
                     f"{a2} higher in {p['a2_higher_in']}); "
                     f"sign p={p['sign_test']['p']}, "
                     f"Wilcoxon p={p['wilcoxon']['p']}")
        L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="append", required=True,
                    help="JSONL (or JSON array) file(s); repeat")
    ap.add_argument("--json", default="", help="write machine summary here")
    args = ap.parse_args(argv)
    rows = load([Path(p) for p in args.data])
    summaries = [analyze_size(rows, sz) for sz in ("small", "medium", "large")]
    print(fmt_md(summaries))
    if args.json:
        Path(args.json).write_text(json.dumps(summaries, indent=2))
        print(f"\n[wrote {args.json}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
