# refactor-granularity (RQ-F) — live campaign

_Auto-generated read-only mirror. Last update: **2026-06-25T21:55:37Z** UTC._

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

## Current status

7. **Campaign running** — this page refreshes about every 10 minutes.

### Overall: 34 / 468 cells complete (7.3%)

- build CORE pass: 34/34 (100%)
- build EDGE pass: 34/34 (100%)
- change-stage pass: 102/102 (100%)
- API-equivalent cost so far: **$36.44**

### Per-arm progress

| arm | cells | cost |
|---|---:|---:|
| `tdd-refactor` | 3/52 | $4.52 |
| `test-after-continuous` | 5/52 | $4.03 |
| `test-after-continuous-frozen` | 5/52 | $4.18 |
| `test-after-continuous-frozen-split` | 3/52 | $3.97 |
| `test-after-continuous-split` | 3/52 | $4.12 |
| `test-after-refactor` | 4/52 | $3.38 |
| `test-after-refactor-frozen` | 5/52 | $4.09 |
| `test-after-refactor-frozen-split` | 3/52 | $3.92 |
| `test-after-refactor-split` | 3/52 | $4.22 |

_Final merged dataset and the analysis report land in `docs/experiments/` on completion._
