# Experiment 05 — Status Report

**Last updated:** 2026-06-27 19:08 UTC

---

## What we're trying to discover

> **To achieve code that is maintainable, well structured, and tested with good tests at minimum cost — which agentic workflow works best?**

AI coding agents can write code in many different ways. We're running a controlled experiment to find out which approach produces the highest-quality output for the lowest price. The three dimensions we're crossing:

| Factor | Levels |
|---|---|
| **Test/code ordering** | Test-first vs. test-after |
| **Batch size** | Small (one behavior at a time) vs. big (everything at once) |
| **Authorship** | One agent does everything vs. two isolated agents (separate coder + tester) |

The four workflow strategies (crossing ordering × batch size):

| Workflow | Strategy |
|---|---|
| **W1 — Classic TDD** | Test-first, small batches (Kent Beck's RED-GREEN-REFACTOR per behavior) |
| **W2 — Code-first, small batches** | Write code, then tests, behavior by behavior |
| **W3 — All code, then all tests** | Write everything in one shot, tests come last |
| **W4 — All tests, then all code** | Write the full failing suite first, then production code to pass it |

W1 with two agents is dropped (TDD is inherently a single integrated loop), giving **7 cells** total.

**What "best" means** is measured across three goals:

- **Maintainability** — radon Maintainability Index, cyclomatic complexity, blast radius across a 3-change chain
- **Test quality** — mutation score, branch coverage, core+edge acceptance pass, test smells
- **Cost** — dollars spent per cell, normalized to quality (quality-per-dollar efficiency frontier)

Refactoring is **always on** — every workflow refactors after each green pass. The experiment fixes this so it is not a variable.

---

## The 7 cells

| Cell | Workflow × Authorship | Arm |
|---|---|---|
| C1 | W1 TDD × 1 agent | `tdd-refactor` |
| C3 | W2 small × 1 agent | `continuous-single` |
| C4 | W2 small × 2 agents | `continuous-split` |
| C5 | W3 big × 1 agent | `one-shot-single` |
| C6 | W3 big × 2 agents | `one-shot-split` |
| C7 | W4 big × 1 agent | `all-tests-first-single` _(new)_ |
| C8 | W4 big × 2 agents | `all-tests-first-split` _(new)_ |

Each cell runs across 4 tasks (`fare`, `payroll`, `cart`, `grades`) × 6 base trials, with sequential extension (up to 12 trials) for any arms whose cost-efficiency ranking remains ambiguous.

---

## Campaign progress

<!-- STATUS_START -->
**Overall:** 220 / 672 rows written — **32% complete**

| Task | Arms complete | Status |
|---|---|---|
| fare | 7 / 7 | ✅ done |
| payroll | 3 / 7 | 🔄 in progress |
| cart | 0 / 7 | ⏳ queued |
| grades | 0 / 7 | ⏳ queued |

_Base campaign: 7 arms × 4 tasks × 6 trials = 168 cells × 4 rows = 672 rows. Sequential extension may add more._

**Campaign started:** 2026-06-27 02:50 UTC — **elapsed: 16h 17m**
<!-- STATUS_END -->


---

## Estimated cost

| Cell | Arm | $/cell | Basis |
|---|---|--:|---|
| C3 | `continuous-single` | $0.99 | run-04 actual |
| C1 | `tdd-refactor` | $1.57 | run-04 actual |
| C5 | `one-shot-single` | $2.01 | run-04 actual |
| C7 | `all-tests-first-single` | ~$2.50 | pilot |
| C4 | `continuous-split` | $2.81 | run-04 actual |
| C6 | `one-shot-split` | $2.85 | run-04 actual |
| C8 | `all-tests-first-split` | ~$3.77 | pilot |
| | **per task × trial (7 arms)** | **~$16.50** | |

**Base campaign estimate: ~$400** (6 trials × 4 tasks × 7 arms). Sequential extension ceiling: ~$790.

---

## Data

Raw results: [`data/refactor-workflow-matrix.jsonl`](data/refactor-workflow-matrix.jsonl)

Model held fixed: `claude-sonnet-4-6`

---

_Updated every 30 minutes while the campaign is running. Status block reflects rows written to disk at update time._
