#!/usr/bin/env python3
"""Pre-registration power calc for the refactor-granularity experiment (RQ-F).

Reads the existing tdd-pays run1+run2 data and estimates whether the proposed
design (4 tasks x 2 clarities, N trials/cell) can detect a 5% difference in
cumulative blast radius between the refactor arms. Run before spending any model
budget — it is the "Power (do this first)" step of
docs/experiments/experiment-prompt-refactor-granularity.md.

Usage: python3 scripts/power_calc_refactor_granularity.py
"""
import glob
import json
import math
import statistics as st
from collections import defaultdict

ALPHA_Z, POWER_Z = 1.96, 0.842  # two-sided alpha=.05, power=.80
DATA = "docs/experiments/data/tdd-pays-*.jsonl"
CHANGE_STAGES = ("change1", "change2", "change3")


def load_cells():
    """cumulative blast (lines added+deleted over the 3-change chain) per cell."""
    cum, seen = defaultdict(int), defaultdict(set)
    for f in glob.glob(DATA):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "tdd-pays" not in r.get("task", ""):
                continue
            br = r.get("blast_radius")
            if not isinstance(br, dict) or r["stage"] not in CHANGE_STAGES:
                continue
            k = (r["task"], r["arm"], r["clarity"], r["trial"])
            cum[k] += (br.get("lines_added") or 0) + (br.get("lines_deleted") or 0)
            seen[k].add(r["stage"])
    return {k: v for k, v in cum.items() if len(seen[k]) == 3}  # complete chains only


def main():
    cells = load_cells()
    bycell = defaultdict(list)
    for (task, arm, clar, _t), v in cells.items():
        bycell[(task, arm, clar)].append(v)
    grand = st.mean(cells.values()) if hasattr(cells, "values") else st.mean(list(cells.values()))
    target = 0.05 * grand
    print(f"complete cells: {len(cells)}   grand mean cumulative blast: {grand:.0f}")
    print(f"5% effect target: {target:.0f} lines\n")

    print("within-cell SD (trial-to-trial stability) by arm:")
    for arm in ("tdd-refactor", "test-after-refactor", "test-after", "tdd-no-refactor"):
        ws = [st.pstdev(v) for (t, a, c), v in bycell.items() if a == arm and len(v) >= 2]
        if ws:
            print(f"  {arm:22s} {st.mean(ws):7.1f}")

    # paired-by-task design (the prompt's stated unit of inference)
    A, B = "tdd-refactor", "test-after-refactor"
    diffs = []
    for (task, arm, clar), vs in bycell.items():
        if arm != A or (task, B, clar) not in bycell:
            continue
        diffs.append(st.median(vs) - st.median(bycell[(task, B, clar)]))
    sdd = st.pstdev(diffs)
    npairs = ((ALPHA_Z + POWER_Z) ** 2) * (sdd / target) ** 2
    print(f"\npaired {A} vs {B}: {len(diffs)} task x clarity units")
    print(f"  mean diff {st.mean(diffs):+.0f}, SD of paired diffs {sdd:.0f}")
    print(f"  paired units needed for 80% power @5% effect: {math.ceil(npairs)}")
    print(f"  => have {len(diffs)}; trials/cell do NOT add paired units, only TASKS do.")

    # unpaired per-cell n, pooled refactor-arm SD
    wsds = [st.pstdev(v) for (t, a, c), v in bycell.items()
            if a in (A, B) and len(v) >= 2]
    sd = st.mean(wsds)
    nper = 2 * ((ALPHA_Z + POWER_Z) ** 2) * (sd / target) ** 2
    print(f"\nunpaired per-cell n (pooled refactor SD {sd:.0f}): {math.ceil(nper)}/cell")


if __name__ == "__main__":
    main()
