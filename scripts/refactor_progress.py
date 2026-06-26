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
import statistics as st
from datetime import datetime

TRIALS, TASKS, ARMS_GOAL = 13, 4, 7
PER_ARM_GOAL = TRIALS * TASKS
SHARDS = "docs/experiments/data/refactor-granularity-*.jsonl"

SUMMARY = """\
## What this experiment is

**Question (RQ-F).** When code is cleaned up, does it matter *how often* you
refactor and *who writes the tests* — for how changeable the code is, how good the
tests are, and what it costs? This follows up an earlier finding that two
refactoring workflows tied on changeability (664 vs 678 lines) — a gap too small to
call at 3 trials.

**Invariant (all arms).** Refactoring is behavior-preserving, so it **does not
change the tests**. Tests change only to express new behavior (the change chain),
never during a refactor step. Refactoring runs as a separate step whose test-file
edits are reverted to the pre-refactor snapshot (a real refactor reverts to a
no-op; an interface-changing "refactor" then fails grading and is caught).

**Two factors, crossed (3x2 = 6 arms) plus a reference (7 arms):**

| factor | levels |
|---|---|
| refactor **granularity** | none / one-shot (one pass at the end) / continuous (after every increment) |
| **authorship** | single agent writes code+tests vs split (independent coder + tester) |

Plus **`tdd-refactor`** (test-first, continuous, single-agent) as an external
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
- **process**: refactor count, attempted test churn during refactor (must be 0 —
  the invariant check), cost per stage
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
5. **Design corrected** — an initial run treated "tests free vs frozen during
   refactor" as a factor; that was wrong (refactoring must not change tests), so the
   invalid arms and their data were discarded and the harness rebuilt around the
   tests-frozen invariant with revert-based enforcement.
6. **Campaign launched** — 7 arms sharded across parallel processes, 4 tasks x 13
   trials, model `claude-sonnet-4-6`.
7. **This live feed** — refreshed every ~10 min while the run proceeds.
"""


def _fmt(seconds):
    seconds = int(max(0, seconds))
    h, m = seconds // 3600, (seconds % 3600) // 60
    return f"~{h}h {m:02d}m" if h else f"~{m} min"


def estimate_eta(now_str, per_done, per_ts):
    """Estimate wall-clock remaining: arms run in parallel, so the slowest governs.

    Per working arm: median recent inter-completion gap x cells remaining, minus
    time already elapsed on the in-flight cell.
    """
    try:
        now = datetime.fromisoformat(now_str.replace("Z", "+00:00"))
    except Exception:
        return "unknown"
    worst = 0.0
    any_working = False
    for arm, done in per_done.items():
        rem = PER_ARM_GOAL - done
        if rem <= 0:
            continue
        any_working = True
        ts = per_ts.get(arm, [])
        gaps = [(b - a).total_seconds() for a, b in zip(ts[-8:], ts[-7:])]
        per = st.median(gaps) if gaps else 900.0
        since = (now - ts[-1]).total_seconds() if ts else 0.0
        worst = max(worst, max(0.0, rem * per - since))
    if not any_working:
        return "—"
    return _fmt(worst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", default="(unknown)")
    args = ap.parse_args()

    per_done, per_cost, per_ts = {}, {}, {}
    cost = 0.0
    cp = cd = ep = ed = chp = chd = 0
    for s in sorted(glob.glob(SHARDS)):
        arm = os.path.basename(s)[len("refactor-granularity-"):-len(".jsonl")]
        done = set()
        ts = []
        c = 0.0
        for line in open(s):
            try:
                r = json.loads(line)
            except Exception:
                continue
            cc = (r.get("cost") or {}).get("cost_usd") or 0
            cost += cc
            c += cc
            stg = r.get("stage")
            if stg == "change3":
                done.add((r["task"], r["trial"]))
                try:
                    ts.append(datetime.fromisoformat(r["ts"]))
                except Exception:
                    pass
            if stg == "build":
                if r.get("core_passed") is not None:
                    cd += 1; cp += 1 if r.get("core_passed") else 0
                if r.get("edge_passed") is not None:
                    ed += 1; ep += 1 if r.get("edge_passed") else 0
            if stg and stg.startswith("change") and r.get("passed") is not None:
                chd += 1; chp += 1 if r.get("passed") else 0
        per_done[arm] = len(done)
        per_cost[arm] = c
        per_ts[arm] = sorted(ts)

    total = sum(per_done.values())
    goal = ARMS_GOAL * PER_ARM_GOAL
    pct = round(100 * total / goal, 1) if goal else 0
    eta = estimate_eta(args.ts, per_done, per_ts)
    if total >= goal and goal:
        phase = "**Campaign complete** — merging shards and running the analysis next."
    else:
        phase = f"**Campaign running** — estimated time remaining: **{eta}**."

    def rate(p, d):
        return f"{p}/{d} ({round(100*p/d)}%)" if d else "—"

    o = ["# refactor-granularity (RQ-F) — live campaign",
         "",
         f"_Auto-generated read-only mirror. Last update: **{args.ts}** UTC._",
         "",
         SUMMARY, STEPS,
         f"## Current status — last updated {args.ts} UTC",
         "",
         "_(this page refreshes at least every 15 minutes while the run is active)_",
         "",
         f"8. {phase}",
         "",
         f"### Overall: {total} / {goal} cells complete ({pct}%)",
         "",
         f"- **estimated time remaining: {eta}**",
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
