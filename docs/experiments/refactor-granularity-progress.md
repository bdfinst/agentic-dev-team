# refactor-granularity (RQ-F) — live campaign

_Auto-generated read-only mirror. Last update: **2026-06-26T00:37:28Z** UTC._

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

## Current status

8. **Campaign running** — this page refreshes about every 10 minutes.

### Overall: 123 / 364 cells complete (33.8%)

- build CORE pass: 123/123 (100%)
- build EDGE pass: 123/123 (100%)
- change-stage pass: 369/369 (100%)
- API-equivalent cost so far: **$178.73**

### Per-arm progress

| arm | cells | cost |
|---|---:|---:|
| `continuous-single` | 25/52 | $24.49 |
| `continuous-split` | 10/52 | $26.65 |
| `no-refactor-single` | 30/52 | $23.67 |
| `no-refactor-split` | 17/52 | $24.18 |
| `one-shot-single` | 13/52 | $25.26 |
| `one-shot-split` | 10/52 | $26.85 |
| `tdd-refactor` | 18/52 | $27.62 |

_Final merged dataset and the analysis report land in `docs/experiments/` on completion._
