# TDD vs. Non-TDD: Does Writing Tests First Pay Off?

**Scope:** Two workflows only — **TDD** (`test-first`, strict RED-GREEN-REFACTOR)
vs **non-TDD** (`test-after`, all production code first, tests written at the end).
The `/plan`→`/build` pipeline arm is **excluded** here; see the full three-arm
study in [`3sizes-3arms-report.md`](3sizes-3arms-report.md).
**Date:** 2026-06-22 · **Model (fixed):** `claude-sonnet-4-6`
**Runner:** [`scripts/run_tdd_experiment.py`](../../scripts/run_tdd_experiment.py) ·
**Analyzer:** [`scripts/analyze_tdd_experiment.py`](../../scripts/analyze_tdd_experiment.py)
**Raw data:** [`data/3sizes-small-sonnet-2026-06-22.jsonl`](data/3sizes-small-sonnet-2026-06-22.jsonl),
[`data/tdd-largetask-sonnet-2026-06-21.json`](data/tdd-largetask-sonnet-2026-06-21.json) (medium),
[`data/3sizes-large-sonnet-2026-06-22.jsonl`](data/3sizes-large-sonnet-2026-06-22.jsonl),
[`data/3sizes-review-findings.json`](data/3sizes-review-findings.json) (review lens)

---

## The question

Holding the model and the task constant, does **writing the tests first**
(strict RED-GREEN-REFACTOR) produce code that is **cheaper, more correct, or
better** than **writing the production code first and the tests at the end**?

Same spec, same hidden acceptance tests, same harness — the *only* variable is
**when the tests are written.** 12 tasks per arm across three sizes (6 small
katas, 6 medium single-module features, 6 large multi-file packages), each cell
isolated and graded by acceptance tests hidden during the build.

## Answer in one line

**No.** At a fixed strong model, TDD is **never cheaper** than test-after, is
**significantly more expensive on mid-sized tasks**, and produces code that is
**equally correct** and **equally (or marginally less) well-tested and clean**.
The differences are all in cost and process, not in the resulting product.

---

## Results — TDD (test-first) vs non-TDD (test-after)

| Size | Correct build | Median cost: TDD | Median cost: non-TDD | TDD/non-TDD | Cov% (TDD/non) | Mutation (TDD/non) | Median turns (TDD/non) |
|---|---|---|---|---|---|---|---|
| small | 100% both | $0.217 | **$0.198** | 1.09× | 100 / 100 | 1.0 / 1.0 | 8 / 8 |
| medium | 100% both | $0.334 | **$0.215** | **1.55×** | 100 / 100 | 1.0 / 1.0 | 17 / 8 |
| large | 100% both | $0.665 | **$0.613** | 1.08× | 98.2 / 97.8 | 0.923 / 0.911 | 14 / 12 |

**non-TDD (test-after) is the cheaper median in every size.** It is also never
worse on coverage or mutation, and runs the same or fewer turns.

## Paired statistics (across the 6 tasks in each size; +Δ ⇒ TDD costs more)

| Size | Median Δ (TDD − non-TDD) | TDD costs more in | Sign p | Wilcoxon p |
|---|---|---|---|---|
| small | +$0.012 | 5/6 tasks | 0.219 | 0.438 |
| medium | +$0.110 | **6/6 tasks** | **0.031** | **0.031** |
| large | +$0.008 | **3/6 (a 3–3 split)** | **1.000** | 0.688 |

**The cost penalty for TDD is real only in the middle.** On medium tasks TDD cost
more on every one of the 6 tasks (+55% median, p=0.031), driven by the extra
RED-GREEN iteration (17 turns vs 8). On small katas the gap is tiny and not
significant; on large multi-file work it **vanishes entirely** — a clean 3–3 split
(p=1.0). The "TDD is more expensive" story does **not** hold uniformly; it peaks
where the task is big enough to add RED-GREEN cycles but small enough that the
per-cycle overhead is a large fraction of the total.

## Correctness

Build-stage correctness is **100% for both arms at every size** (small 18/18,
medium 6/6, large 18/18 each). On the **withheld Stage-2 change** — a behaviour
modification revealed only after the build — the large tier is the only place
either arm slips, and it slips *against* TDD:

| | TDD change-pass | non-TDD change-pass |
|---|---|---|
| small | 17/18 | 17/18 |
| medium | 6/6 | 6/6 |
| large | **15/18** | **17/18** |

With 1–3 failures per 18 cells this is within noise, but it is worth stating
plainly: **the "test-first gives you a safety net that makes change safer"
hypothesis did not show up** — if anything, test-after changed the large packages
slightly more reliably. The agent's own test suite (hidden acceptance aside) did
not visibly protect the test-first arm better during the change.

## Test quality (coverage + mutation, build stage)

Identical for practical purposes. Small and medium katas pin **both** arms at
**100% coverage / 1.0 mutation** — saturated, no signal. The large tier is the
only place the sensors have resolution, and the arms are a dead heat:
**coverage 98.2% (TDD) vs 97.8% (non-TDD); mutation 0.923 vs 0.911** — inside the
noise. **There is no "test-first writes stronger tests" signal in the data.**

## Code quality — the review lens (large tier)

Coverage/mutation are blind to code structure, so one build-stage solution per arm
for the 6 large tasks was graded by a 6-agent review panel (`structure`,
`complexity`, `naming`, `performance`, `security`, `test-review`); findings
weighted critical=4 / high=3 / medium=2 / low=1.

| Arm | Critical | High | Medium | Low | Weighted | Median/task |
|---|---|---|---|---|---|---|
| **non-TDD (test-after)** | 4 | 10 | 14 | 17 | **91** | 15.0 |
| TDD (test-first) | 3 | 14 | 18 | 18 | 108 | 19.0 |

Paired across the 6 tasks: **non-TDD was the cleaner arm in 4/6, TDD in 1/6, 1
tie** (median Δ = +3.5 weighted against TDD, **sign p = 0.375** — not
significant). TDD's extra findings came mostly from `complexity-review` — strict
RED-GREEN-REFACTOR left longer, more deeply-nested functions on the
parser-heavy tasks (spreadsheet, template-engine, router), suggesting the
**REFACTOR step under-delivered on structure**. So on the one axis where code
quality is even measurable, TDD is **directionally a touch worse, not better** —
though with real reviewer run-to-run variance and n=6, treat this as "no
advantage," not "test-after wins."

## What this means

- **TDD did not produce cheaper code.** non-TDD was the cheaper median in all
  three sizes; TDD was significantly more expensive only on mid-sized tasks and
  tied elsewhere.
- **TDD did not produce more correct code.** Both arms were 100% correct on the
  build; on the withheld change TDD was, if anything, marginally behind on large.
- **TDD did not produce better-tested code.** Coverage and mutation were identical
  (saturated on small/medium, a dead heat on large).
- **TDD did not produce cleaner code.** On the only size where structure is
  measurable, TDD drew *more* review findings (directionally, not significantly),
  concentrated in complexity.

The case for TDD here is therefore **not** "cheaper, more correct, or better
output" at this model strength. Its value, if any, is **process**: an executable
spec that forces the agent to state intended behaviour before coding, a guard
against the LLM's strong tendency to write implementation-first and tests-later
(or never), and human-legible incremental steps. Those are real benefits — but
this experiment measures *output*, and on output, **TDD and non-TDD are
indistinguishable except that TDD costs the same or more.**

## Limitations

- **n = 6 tasks per size**; exact paired tests bottom out near p≈0.03. Single-size
  results are directional; the cross-size *pattern* (TDD penalty peaks at medium,
  vanishes at large) is the durable signal.
- **Single model** (`claude-sonnet-4-6`). Prior work showed the cost winner flips
  with model — on a weaker model (haiku) an earlier run found test-first *cheaper*
  on small katas. This report is sonnet-only.
- **Medium tier folded from the 2026-06-21 sonnet run (N=1/trial)**; small/large
  are N=3. Same model/tasks/harness.
- **The review lens is N=1 per cell** with measurable reviewer variance — its
  "test-after slightly cleaner" result is suggestive, not settled.
- **Output-only.** This measures cost, correctness, test-quality sensors, and
  review findings. It does *not* measure TDD's process benefits (design pressure,
  refactoring confidence, human review load) — which are the usual reasons to
  adopt it.

## Reproducibility

```bash
pip install coverage pytest
# instruction arms only, per task, 3 trials:
python3 scripts/run_tdd_experiment.py --arm test-first --arm test-after \
  --only "<task>" --trials 3 --model claude-sonnet-4-6 --out out.jsonl
python3 scripts/analyze_tdd_experiment.py \
  --data data/3sizes-small-sonnet-2026-06-22.jsonl \
  --data data/tdd-largetask-sonnet-2026-06-21.json \
  --data data/3sizes-large-sonnet-2026-06-22.jsonl
# (read the test-first / test-after rows; ignore build-pipeline)
```

## Recommendation

- **Do not adopt strict test-first expecting cheaper, more-correct, or
  better-tested code at this model strength** — it delivers none of those here and
  costs the same or more (notably +55% on mid-sized tasks).
- **If you use TDD, use it for its process discipline**, not its output: the
  executable-spec-first habit and protection against implementation-first drift.
- **Strengthen the REFACTOR step.** TDD's only measurable output gap was *worse*
  structure (more complexity findings) because RED-GREEN-REFACTOR is stopping at
  GREEN. Wiring `refactor-opportunity-review` / `complexity-review` into the
  REFACTOR phase would remove the one place TDD currently loses on output.
