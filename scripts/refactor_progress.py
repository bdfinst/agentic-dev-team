#!/usr/bin/env python3
"""Render the live refactor-granularity campaign page as Markdown.

Leads with a static summary of the experiment and the steps taken, then a live
status section computed from the per-arm shard JSONL files. Used for the public
read-only progress mirror committed to the branch and for local status checks.

Usage: python3 scripts/refactor_progress.py [--ts ISO8601]
"""
import argparse
import glob
import json
import os

TRIALS, TASKS, ARMS_GOAL = 13, 4, 7
PER_ARM_GOAL = TRIALS * TASKS
SHARDS = "docs/experiments/data/refactor-granularity-*.jsonl"

SUMMARY = """\
## What this experiment is

**Question (RQ-F).** When code is cleaned up, does it matter *how often* you
refactor, *whether the tests are allowed to change* while you do, and *who writes
the tests*? And what does any difference cost? This follows up an earlier finding
that the two refactoring workflows tied on changeability (664 vs 678 lines) — a
gap too small to call at 3 trials. This run is built to tell a real difference
from noise and to separate the mechanisms behind it.

**Three factors, crossed (2x2x2 = 8 arms) plus a reference (9 arms):**

| factor | levels |
|---|---|
| refactor **granularity** | one-shot (a single pass at the end) vs continuous (after every increment) |
| test **protection** during the refactor | free (tests may change) vs frozen (tests locked) |
| **authorship** | single agent writes code+tests vs split (independent coder + tester) |

Plus **`tdd-refactor`** (continuous, test-first, single-agent) as an external
reference. **Clear specifications only**; no spec-plan-build arm.

**Each cell** = build the feature, then apply a **3-change chain** that modifies
behavior (stressing the suite as a safety net). Run as **4 tasks x 13 trials**.

**Tasks** (authored clean-room; each has a hidden acceptance suite and a change
chain whose trap punishes non-modular code): `fare` (transit fares), `payroll`
(net pay), `cart` (checkout totals), `grades` (weighted gradebook).

**What every cell measures** — three axes, reported raw *and* per-dollar:
- **changeability**: lines touched to absorb each change (blast radius)
- **modularity**: radon (complexity, maintainability) + lizard
- **test quality**: CORE/EDGE acceptance, mutation score, branch coverage, smells
- **process**: refactor granularity, test-LOC churn during refactor (also the
  frozen-compliance check), cost per stage
"""

STEPS = """\
## Steps taken so far

1. **Clean-room harness built** (`scripts/run_refactor_experiment.py`) — per-cell
   isolation (own worktree + scratch HOME), build + 3-change chain, tagged-commit
   churn/granularity sensors, and defensive blast-radius / radon+lizard / mutation
   / coverage / smell / acceptance sensors. Validated with no model cost.
2. **Four tasks authored from scratch** — reference solutions + ~120 hidden
   acceptance tests total, every one green against its reference (independently
   re-validated).
3. **Pilot** — one real cell end-to-end: all stages passing, ~$0.93, sensors
   correct (coverage, mutation, blast radius, granularity).
4. **Runner hardened** — resume (skips completed cells) + dispatch retry; the
   split-authorship build made a faithful 3-phase flow (coder -> independent
   tester -> coder refactor under the protection rule).
5. **Campaign launched** — 9 arms sharded across parallel processes, 4 tasks x 13
   trials, model `claude-sonnet-4-6`.
6. **This live feed** — refreshed every ~10 min while the run proceeds.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", default="(unknown)")
    args = ap.parse_args()

    per_done, per_cost = {}, {}
    cost = 0.0
    cp = cd = ep = ed = chp = chd = 0
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
                    cd += 1; cp += 1 if r.get("core_passed") else 0
                if r.get("edge_passed") is not None:
                    ed += 1; ep += 1 if r.get("edge_passed") else 0
            if st and st.startswith("change") and r.get("passed") is not None:
                chd += 1; chp += 1 if r.get("passed") else 0
        per_done[arm] = len(done)
        per_cost[arm] = c

    total = sum(per_done.values())
    goal = ARMS_GOAL * PER_ARM_GOAL
    pct = round(100 * total / goal, 1) if goal else 0
    phase = ("**Campaign complete** — merging shards and running the analysis next."
             if total >= goal and goal else
             "**Campaign running** — this page refreshes about every 10 minutes.")

    def rate(p, d):
        return f"{p}/{d} ({round(100*p/d)}%)" if d else "—"

    o = ["# refactor-granularity (RQ-F) — live campaign",
         "",
         f"_Auto-generated read-only mirror. Last update: **{args.ts}** UTC._",
         "",
         SUMMARY, STEPS,
         "## Current status",
         "",
         f"7. {phase}",
         "",
         f"### Overall: {total} / {goal} cells complete ({pct}%)",
         "",
         f"- build CORE pass: {rate(cp, cd)}",
         f"- build EDGE pass: {rate(ep, ed)}",
         f"- change-stage pass: {rate(chp, chd)}",
         f"- API-equivalent cost so far: **${cost:.2f}**",
         "",
         "### Per-arm progress",
         "",
         "| arm | cells | cost |",
         "|---|---:|---:|"]
    for arm in sorted(per_done):
        o.append(f"| `{arm}` | {per_done[arm]}/{PER_ARM_GOAL} | ${per_cost[arm]:.2f} |")
    o += ["",
          "_Final merged dataset and the analysis report land in "
          "`docs/experiments/` on completion._"]
    print("\n".join(o))


if __name__ == "__main__":
    main()
