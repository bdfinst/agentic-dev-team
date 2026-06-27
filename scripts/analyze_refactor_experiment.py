#!/usr/bin/env python3
"""Analyze the refactoring-cadence campaign (granularity x authorship).

Reads the merged JSONL and reports the three axes per arm and per factor:
changeability (cumulative blast radius), modularity (radon/lizard), test quality
(CORE/EDGE, mutation, coverage, smells), and cost (+ per-dollar ratios). The unit
of inference is the task: per-arm-per-task medians across trials, compared across
the 4 tasks. Prints a readable summary and writes a JSON summary.

Usage: python3 scripts/analyze_refactor_experiment.py
"""
import glob
import json
import statistics as st
from collections import defaultdict

MERGED = "docs/experiments/data/refactor-granularity-merged.jsonl"
OUT = "docs/experiments/data/refactor-granularity-summary.json"
ARMS = ["tdd-refactor", "no-refactor-single", "one-shot-single", "continuous-single",
        "no-refactor-split", "one-shot-split", "continuous-split"]


def load():
    cells = defaultdict(dict)  # (task,arm,trial) -> {stage: row}
    for l in open(MERGED):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        cells[(r["task"], r["arm"], r["trial"])][r["stage"]] = r
    return cells


def cell_metrics(stages):
    """Derive per-cell metrics from its 4 stage rows."""
    b = stages.get("build")
    if not b:
        return None
    changes = [stages.get(f"change{i}") for i in (1, 2, 3)]
    if not all(changes):
        return None
    cum_blast = sum((c.get("blast_radius") or {}).get("churned", 0) for c in changes)
    cost = sum((stages.get(s, {}).get("cost") or {}).get("cost_usd") or 0
               for s in ("build", "change1", "change2", "change3"))
    return {
        "cum_blast": cum_blast,
        "cost": cost,
        "core": 1 if b.get("core_passed") else 0,
        "edge": 1 if b.get("edge_passed") else 0,
        "change_pass": 1 if all(c.get("passed") for c in changes) else 0,
        "mutation": (b.get("mutation") or {}).get("score"),
        "coverage": (b.get("coverage") or {}).get("percent"),
        "mi": (b.get("radon") or {}).get("avg_mi"),
        "cc": (b.get("radon") or {}).get("avg_cc"),
        "ccn": (b.get("lizard") or {}).get("avg_ccn"),
        "smells": (b.get("smells") or {}).get("assertless_tests", 0),
        "test_loc": (b.get("smells") or {}).get("test_loc"),
        "violation": 1 if b.get("invariant_violation") else 0,
        "granularity": b.get("granularity"),
        "authorship": b.get("authorship"),
    }


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 2) if xs else None


def main():
    cells = load()
    # per cell metrics
    per_cell = {}
    for k, stages in cells.items():
        m = cell_metrics(stages)
        if m:
            per_cell[k] = m

    # task-level medians: (arm, task) -> metric medians across trials
    by_arm_task = defaultdict(lambda: defaultdict(list))
    by_arm = defaultdict(lambda: defaultdict(list))
    for (task, arm, trial), m in per_cell.items():
        for key in ("cum_blast", "cost", "mutation", "coverage", "mi", "cc", "ccn",
                    "test_loc", "core", "edge", "change_pass", "violation"):
            by_arm_task[(arm, task)][key].append(m[key])
            by_arm[arm][key].append(m[key])

    summary = {"n_cells": len(per_cell), "arms": {}}
    print(f"\n{'='*92}\nrefactor-granularity results — {len(per_cell)} complete cells\n{'='*92}")
    hdr = (f"{'arm':22s}{'cum_blast':>10s}{'cost$':>8s}{'blast/$':>9s}"
           f"{'mut':>6s}{'cov%':>6s}{'MI':>7s}{'CCN':>6s}{'CORE':>6s}{'EDGE':>6s}{'viol':>5s}")
    print(hdr)
    print("-" * 92)
    for arm in ARMS:
        d = by_arm[arm]
        # task-paired medians: median across the 4 task-medians
        tasks = sorted({t for (a, t) in by_arm_task if a == arm})
        blast_taskmed = [med(by_arm_task[(arm, t)]["cum_blast"]) for t in tasks]
        cost_taskmed = [med(by_arm_task[(arm, t)]["cost"]) for t in tasks]
        cb = med(blast_taskmed)
        co = med(cost_taskmed)
        mut = med(d["mutation"]); cov = med(d["coverage"]); mi = med(d["mi"])
        ccn = med(d["ccn"])
        core = round(100 * st.mean(d["core"])); edge = round(100 * st.mean(d["edge"]))
        viol = sum(d["violation"])
        bpd = round(cb / co, 1) if cb and co else None
        summary["arms"][arm] = dict(cum_blast=cb, cost=co, blast_per_dollar=bpd,
                                    mutation=mut, coverage=cov, mi=mi, ccn=ccn,
                                    core_pass=core, edge_pass=edge, violations=viol,
                                    blast_by_task=blast_taskmed)
        print(f"{arm:22s}{cb:>10.1f}{co:>8.2f}{(bpd or 0):>9.1f}"
              f"{(mut or 0):>6.2f}{(cov or 0):>6.0f}{(mi or 0):>7.1f}{(ccn or 0):>6.1f}"
              f"{core:>5d}%{edge:>5d}%{viol:>5d}")

    # factor main effects (median of arm cum_blast within each level)
    def factor(level_key, level):
        arms = [a for a in ARMS if a != "tdd-refactor"
                and per_arm_factor(a, level_key) == level]
        blasts = [summary["arms"][a]["cum_blast"] for a in arms]
        costs = [summary["arms"][a]["cost"] for a in arms]
        return med(blasts), med(costs), arms

    print(f"\n{'-'*60}\nFactor main effects (test-after grid, tdd-refactor excluded)\n{'-'*60}")
    gran_eff = {}
    for g in ("none", "one-shot", "continuous"):
        arms = [a for a in ("no-refactor-single", "one-shot-single", "continuous-single",
                            "no-refactor-split", "one-shot-split", "continuous-split")
                if summary_gran(a) == g]
        b = med([summary["arms"][a]["cum_blast"] for a in arms])
        c = med([summary["arms"][a]["cost"] for a in arms])
        mi = med([summary["arms"][a]["mi"] for a in arms])
        gran_eff[g] = dict(cum_blast=b, cost=c, mi=mi)
        print(f"  granularity={g:11s} cum_blast={b}  cost=${c}  MI={mi}")
    auth_eff = {}
    for au in ("single", "split"):
        arms = [a for a in ARMS if a != "tdd-refactor" and a.endswith(au)]
        b = med([summary["arms"][a]["cum_blast"] for a in arms])
        c = med([summary["arms"][a]["cost"] for a in arms])
        mut = med([summary["arms"][a]["mutation"] for a in arms])
        edge = med([summary["arms"][a]["edge_pass"] for a in arms])
        auth_eff[au] = dict(cum_blast=b, cost=c, mutation=mut, edge_pass=edge)
        print(f"  authorship={au:8s} cum_blast={b}  cost=${c}  mutation={mut}  EDGE={edge}%")
    summary["granularity_effect"] = gran_eff
    summary["authorship_effect"] = auth_eff

    json.dump(summary, open(OUT, "w"), indent=2)
    print(f"\nwrote {OUT}")


def summary_gran(arm):
    return {"no-refactor-single": "none", "one-shot-single": "one-shot",
            "continuous-single": "continuous", "no-refactor-split": "none",
            "one-shot-split": "one-shot", "continuous-split": "continuous"}[arm]


def per_arm_factor(arm, key):
    return None


if __name__ == "__main__":
    main()
