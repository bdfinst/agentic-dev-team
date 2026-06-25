#!/usr/bin/env python3
"""Render a live progress snapshot of the refactor-granularity campaign as Markdown.

Reads the per-arm shard JSONL files and prints a Markdown page to stdout. Used
both for the public read-only progress mirror and for local status checks.

Usage: python3 scripts/refactor_progress.py [--ts ISO8601]
"""
import argparse
import glob
import json
import os

TRIALS, TASKS = 13, 4
PER_ARM_GOAL = TRIALS * TASKS
ARMS_GOAL = 9
SHARDS = "docs/experiments/data/refactor-granularity-*.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", default="(unknown)", help="UTC timestamp string")
    args = ap.parse_args()

    per_arm_done, per_arm_cost = {}, {}
    cost = 0.0
    core_pass = core_den = edge_pass = edge_den = 0
    change_pass = change_den = 0
    for s in sorted(glob.glob(SHARDS)):
        arm = os.path.basename(s)[len("refactor-granularity-"):-len(".jsonl")]
        done = set()
        c = 0.0
        for line in open(s):
            try:
                r = json.loads(line)
            except Exception:
                continue
            cc = (r.get("cost") or {}).get("cost_usd") or 0
            cost += cc
            c += cc
            st = r.get("stage")
            if st == "change3":
                done.add((r["task"], r["trial"]))
            if st == "build":
                if r.get("core_passed") is not None:
                    core_den += 1
                    core_pass += 1 if r.get("core_passed") else 0
                if r.get("edge_passed") is not None:
                    edge_den += 1
                    edge_pass += 1 if r.get("edge_passed") else 0
            if st and st.startswith("change") and r.get("passed") is not None:
                change_den += 1
                change_pass += 1 if r.get("passed") else 0
        per_arm_done[arm] = len(done)
        per_arm_cost[arm] = c

    total = sum(per_arm_done.values())
    goal = ARMS_GOAL * PER_ARM_GOAL
    pct = round(100 * total / goal, 1) if goal else 0

    def rate(p, d):
        return f"{p}/{d} ({round(100*p/d)}%)" if d else "—"

    out = []
    out.append("# refactor-granularity — live campaign progress")
    out.append("")
    out.append(f"_Auto-generated read-only mirror. Last update: **{args.ts}**_")
    out.append("")
    out.append("Experiment RQ-F: does *how* you refactor (granularity), *whether tests "
               "are frozen* during it, and *who writes the tests* (authorship) change "
               "code changeability and test quality? 9 arms x 4 tasks x 13 trials, "
               "clear specs, build + 3-change chain.")
    out.append("")
    out.append(f"## Overall: {total} / {goal} cells complete ({pct}%)")
    out.append("")
    out.append(f"- build CORE pass: {rate(core_pass, core_den)}")
    out.append(f"- build EDGE pass: {rate(edge_pass, edge_den)}")
    out.append(f"- change-stage pass: {rate(change_pass, change_den)}")
    out.append(f"- API-equivalent cost so far: **${cost:.2f}**")
    out.append("")
    out.append("## Per-arm progress")
    out.append("")
    out.append("| arm | granularity x protection x authorship | cells | cost |")
    out.append("|---|---|---:|---:|")
    for arm in sorted(per_arm_done):
        bar_done = per_arm_done[arm]
        out.append(f"| `{arm}` | | {bar_done}/{PER_ARM_GOAL} | ${per_arm_cost[arm]:.2f} |")
    out.append("")
    out.append("Final merged data and the analysis report land in "
               "`docs/experiments/` on completion.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
