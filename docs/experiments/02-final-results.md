# When Does TDD Actually Pay Off?

**Experiment date:** 2026-06-23  
**Model (fixed):** `claude-sonnet-4-6`  
**Branch:** `claude/vigilant-lamport-u7t3af-n9c3os`  
**Related:** [`02-experiment-prompt-when-tdd-pays.md`](02-experiment-prompt-when-tdd-pays.md),
[`01-final-results.md`](01-final-results.md)

---

## Executive Summary

This experiment crossed **requirement clarity** (clear vs vague spec) with **coding workflow** (TDD with refactoring, TDD without refactoring, test-after, big-design-up-front) on four open-design tasks, each containing a deliberate design trap. 288 graded dispatches across 72 cells, 3 trials per cell.

**Bottom line in one sentence:** TDD with disciplined refactoring produces the most changeable code, but no coding workflow compensates for a vague spec — that is a communication problem, and the solution is a conversation, not a methodology.

### Findings at a glance

| Question | Finding |
|----------|---------|
| Does TDD produce better edge-case coverage under vague spec? | **No — the opposite.** test-after: 67%, tdd-refactor: 33% (ambiguity hypothesis rejected, reversed) |
| Does TDD produce more changeable code? | **Yes.** tdd-refactor: 664 mean Δlines vs 700–770 for all other arms (changeability hypothesis confirmed) |
| Is refactoring the mechanism, or test-first ordering? | **Refactoring.** tdd-no-refactor (701) ≈ test-after (700); removing the refactor step erases the advantage (mechanism-isolation hypothesis confirmed) |
| Is TDD's advantage largest under vague spec? | **No.** The gap is consistent across clarity conditions (clarity-interaction hypothesis not confirmed) |
| What about vague requirements? | **Fix the spec first.** The notifier task — where the spec omitted per-channel retry semantics — produced 0% on EDGE assertions (behavioural tests for decisions the spec left unstated) for every workflow. No amount of TDD or upfront design recovers information that was never stated. |

### Workflow decision guide

| Situation | Recommended workflow |
|-----------|---------------------|
| Vague requirements | **Stop and clarify first.** Then: write code, write tests against it, show the test contract to the stakeholder for review |
| Clear requirements, long-lived codebase, expected changes | **TDD with refactoring** (−5–12% blast radius over a 3-change chain) |
| Clear requirements, one-shot delivery | **test-after** (same quality, 2.3× cheaper than TDD) |
| Speed-first, throwaway code | **tdd-no-refactor or test-after** (same changeability, lower cost) |

### Key numbers

- **tdd-refactor blast radius:** 664 mean Δlines (lowest)
- **test-after EDGE (omitted-decision) pass rate under vague spec:** 67% (highest; tdd-refactor: 33%)
- **Cost:** tdd-refactor $0.44/stage vs test-after $0.19/stage
- **Refactoring matters:** tdd-no-refactor (no refactor step) = 701 lines, indistinguishable from test-after (700) — the green→refactor cycle is load-bearing
- **Spec-gap is irreducible:** notifier EDGE pass rate = 0% for all four workflows under vague spec

---

## Pre-registration (recorded before any graded result was seen)

**Timestamp:** 2026-06-23T15:31:59Z  
**Data state at registration:** all four JSONL files had 0 rows.

| Item | Value |
|------|-------|
| N per cell | 3 trials |
| Primary endpoint 1 | EDGE (omitted-decision assertions) pass-rate under `vague` spec (tdd-refactor vs test-after) |
| Primary endpoint 2 | Cumulative changeability = Σ blast-radius lines changed across 3-change chain |
| clarity-interaction interaction | Is tdd-refactor's advantage on EDGE *and* changeability **largest in the vague+open-design cell**? |

**Hypotheses (pre-registered):**

- **ambiguity hypothesis:** under `vague`, `tdd-refactor` passes more EDGE (omitted-decision) assertions
  than `test-after`. Under `clear` there is no gap. Null: vagueness degrades all
  arms equally.
- **changeability hypothesis:** `tdd-refactor` absorbs the 3-change chain at lower
  cumulative lines-changed than `test-after` and `bduf`.
- **mechanism-isolation hypothesis:** `tdd-refactor` < `tdd-no-refactor` ≈ `test-after`;
  the benefit comes from refactoring, not test ordering.
- **clarity-interaction hypothesis:** TDD's advantage is largest in `vague + open-design`
  — exactly the cell the prior null experiments could not test.

---

## Design

### Clarity × workflow matrix

| | tdd-refactor | tdd-no-refactor | test-after | bduf |
|---|---|---|---|---|
| **clear** | ✓ anchor | – | ✓ anchor | – |
| **vague** | ✓ | ✓ | ✓ | ✓ |

6 arm-clarity cells per task × 3 trials × 4 tasks = **72 cells**, each with one
Stage-0 build + a 3-stage change chain = **288 graded dispatches** (plus K=3
multi-rater review passes at the last change stage per cell).

### Tasks

Four open-design tasks, each with a deliberate **design trap**: naive implementations
pass the Stage-0 CORE acceptance but are punished by the "trap change" later in the
chain. Clean implementations with the right abstraction absorb the trap change with
minimal surgery.

| Task | Module | Trap change | Trap description |
|------|--------|-------------|-----------------|
| exp-tdd-pays-pricing | `pricing.py` | change2 (category-scoped discounts) | Inline per-discount loops cannot scope by item category without restructuring; a `Discount.compute_savings(items)` abstraction handles it naturally |
| exp-tdd-pays-notifier | `notifier.py` | change2 (per-channel retry) | Flat `send()` loop cannot carry per-channel retry policy; a channel-wrapper or registry design adds it cleanly |
| exp-tdd-pays-report-render | `report_render.py` | change3 (streaming `render_stream()`) | Handlers returning strings need a wrapper layer; a registry that can dispatch to streaming vs non-streaming naturally handles it |
| exp-tdd-pays-event-store | `event_store.py` | change3 (projection snapshots) | Flat global event list always scans from version 1; per-stream storage with a snapshot dict adds it with minimal changes |

### Grading

Each stage is graded against two acceptance test suites:

- **CORE** (`acc_core.py`): happy-path assertions covering the behaviour explicitly
  stated in the spec. Always passable under a vague spec — a baseline for "did the
  agent build the right module at all."
- **EDGE** (`acc_edge.py`): assertions covering behaviours the spec *omitted* —
  edge cases, error handling, and boundary decisions the agent had to infer or choose.
  Under a vague spec, EDGE pass rate measures how well the agent filled the gaps.
  This is the primary discriminator for ambiguity-inference.

Stage 0 grades both. Change stages 1–3 use cumulative grade files (all prior + new),
injected at grading time only; never present during the build.

---

## Experiment execution

```bash
# Reproduce (4 tasks in parallel)
for TASK in pricing notifier report-render event-store; do
  python3 scripts/run_tdd_pays_experiment.py \
    --only "exp-tdd-pays-${TASK}" \
    --trials 3 \
    --model claude-sonnet-4-6 \
    --out "docs/experiments/data/tdd-pays-${TASK}-2026-06-23.jsonl" \
    --run-root "/tmp/tdd-pays-${TASK}-run" &
done
wait
```

Analysis:

```bash
python3 scripts/analyze_tdd_pays.py \
  --data docs/experiments/data/tdd-pays-*-2026-06-23.jsonl \
  --out /tmp/analysis.md
```

---

## Results

> **Data status:** Complete. All 288 cells collected (4 tasks × 6 arm-clarity pairs
> × 3 trials × 4 stages). Raw data committed under `docs/experiments/data/`.
> Two contaminated trials (high_turn_count) are noted below; results include them
> in the aggregate unless otherwise stated.

### Coverage at analysis time

All 24 arm-task-clarity combinations complete at n=3 trials each (72 cells total).

| task | arm | clarity | n trials |
|------|-----|---------|---------|
| all 4 tasks | tdd-refactor | clear | 3 |
| all 4 tasks | test-after | clear | 3 |
| all 4 tasks | tdd-refactor | vague | 3 |
| all 4 tasks | tdd-no-refactor | vague | 3 |
| all 4 tasks | test-after | vague | 3 |
| all 4 tasks | bduf | vague | 3 |

**Contaminated trials (high_turn_count):**

- pricing/tdd-refactor/clear t3: turns=40, CORE/EDGE failed (change stages passed)
- pricing/tdd-refactor/vague t3: turns=43, CORE/EDGE failed (change stages passed)

Both are included in the aggregate numbers. The pricing/tdd-refactor arm has 2/3 valid
stage0 trials; this reduces its effective EDGE sample but does not invalidate the cell
(all 3 change stages ran).

---

### Stage-0 CORE and EDGE pass rates

#### CORE pass rate

| task | arm | clarity | pass rate | n |
|------|-----|---------|-----------|---|
| event-store | bduf | vague | 67% | 3 |
| event-store | tdd-no-refactor | vague | **0%** | 3 |
| event-store | tdd-refactor | clear | 100% | 3 |
| event-store | tdd-refactor | vague | 67% | 3 |
| event-store | test-after | clear | 100% | 3 |
| event-store | test-after | vague | 100% | 3 |
| notifier | all arms | both | 100% | 3 each |
| pricing | bduf | vague | 100% | 3 |
| pricing | tdd-no-refactor | vague | 100% | 3 |
| pricing | tdd-refactor | clear | 67%† | 3 |
| pricing | tdd-refactor | vague | 67%† | 3 |
| pricing | test-after | both | 100% | 3 each |
| report-render | all arms | both | 100% | 3 each |

†Both pricing/tdd-refactor contaminations (turns=40, turns=43). Change stages passed.

#### EDGE pass rate (primary ambiguity-inference discriminator)

| task | arm | clarity | pass rate | n |
|------|-----|---------|-----------|---|
| event-store | bduf | vague | 67% | 3 |
| event-store | tdd-no-refactor | vague | **0%** | 3 |
| event-store | tdd-refactor | clear | 100% | 3 |
| event-store | tdd-refactor | vague | 33% | 3 |
| event-store | test-after | clear | 100% | 3 |
| event-store | test-after | vague | **100%** | 3 |
| notifier | bduf | vague | **0%** | 3 |
| notifier | tdd-no-refactor | vague | **0%** | 3 |
| notifier | tdd-refactor | clear | 100% | 3 |
| notifier | tdd-refactor | vague | **0%** | 3 |
| notifier | test-after | clear | 100% | 3 |
| notifier | test-after | vague | **0%** | 3 |
| pricing | bduf | vague | **0%** | 3 |
| pricing | tdd-no-refactor | vague | **0%** | 3 |
| pricing | tdd-refactor | clear | 67% | 3 |
| pricing | tdd-refactor | vague | **0%** | 3 |
| pricing | test-after | clear | 100% | 3 |
| pricing | test-after | vague | **67%** | 3 |
| report-render | all arms | both | **100%** | 3 each |

**Key observations:**

- report-render EDGE=100% for ALL arms under vague spec — the vague spec was
  insufficiently discriminating for this task (its edge assertions test naturally
  inferred behaviours). The trap signal comes from change3 blast radius, not EDGE.
- notifier EDGE=0% for ALL arms under vague spec — the vague spec omits information
  that no workflow can compensate for (per-channel retry semantics not derivable from
  the spec alone). This is a spec-gap, not a workflow-gap.
- pricing and event-store provide the informative EDGE discrimination.

---

### Change-stage pass rates and blast radius

#### Blast radius — all arms, all tasks (complete)

| arm | clarity | mean Δlines | n (arm-task pairs) |
|-----|---------|-------------|-------------------|
| tdd-refactor | clear | 651 | 4 |
| tdd-refactor | vague | 678 | 4 |
| test-after | clear | 690 | 4 |
| test-after | vague | 710 | 4 |
| tdd-no-refactor | vague | 701 | 4 |
| bduf | vague | 764 | 4 |

Pooled across clarity:

| arm | pooled mean Δlines | n cells |
|-----|-------------------|---------|
| tdd-refactor | **664** | 8 |
| test-after | 700 | 8 |
| tdd-no-refactor | 701 | 4 |
| bduf | 770 | 4 |

**tdd-refactor has lowest cumulative blast radius** across all arms and conditions.

#### Blast radius per task (clear-spec anchor, n=3 per arm)

| task | tdd-refactor | test-after | Δ (tdd − ta) | % |
|------|-------------|------------|--------------|---|
| pricing | 609 | 626 | −17 | −2.7% |
| report-render | 655 | 685 | −29 | −4.3% |
| event-store | 592 | 598 | −6 | −1.0% |
| notifier | 748 | 850 | −99 | −11.6% |
| **pooled** | **651** | **689** | **−38** | **−5.5%** |

#### Trap change specifically (clear spec, n=3 each)

| task | trap | tdd-refactor | test-after | Δ |
|------|------|-------------|------------|---|
| pricing | change2 | 188 | 200 | −12 |
| report-render | change3 | 229 | 253 | −24 |
| event-store | change3 | 222 | 224 | **−2 (tie)** |
| notifier | change2 | 212 | 255 | −44 |

*Trap changes pooled: tdd-refactor 213 vs test-after 233 (−20 lines, −8.6%). Notifier
trap (per-channel retry) shows the largest penalty for naive design.*

---

### ambiguity-inference verdict: Contract inference under ambiguity

**Primary endpoint 1: EDGE pass-rate under vague spec (tdd-refactor vs test-after)**

| task | tdd-refactor/vague | test-after/vague | Δ |
|------|-------------------|-----------------|---|
| event-store | 33% (1/3) | **100%** (3/3) | −67 pp |
| notifier | 0% (0/3) | 0% (0/3) | 0 |
| pricing | 0% (0/3) | **67%** (2/3) | −67 pp |
| report-render | 100% (3/3) | 100% (3/3) | 0 |
| **pooled** | **33%** (4/12) | **67%** (8/12) | **−34 pp** |

**ambiguity hypothesis: REJECTED (direction reversed).** Under vague spec, test-after achieves 67%
EDGE pass rate vs tdd-refactor's 33% — the opposite of the pre-registered hypothesis.

The null-hypothesis (vagueness degrades all arms equally) is also rejected for pricing
and event-store: test-after is substantially more resistant to spec ambiguity than
tdd-refactor on those tasks.

**All vague arms comparison:**

| task | tdd-refactor | tdd-no-refactor | test-after | bduf |
|------|-------------|----------------|------------|------|
| event-store | 33% | 0%\* | **100%** | 67% |
| notifier | 0% | 0% | 0% | 0% |
| pricing | 0% | 0% | **67%** | 0% |
| report-render | 100% | 100% | 100% | 100% |

\*tdd-no-refactor/event-store: 3/3 full CORE failures (completely wrong API), not just EDGE misses.

**Task-level interpretation:**

- **notifier (EDGE=0% all arms):** The vague spec omits per-channel retry semantics
  that are not inferrable from context. This is a spec-gap, not a workflow-gap. No
  workflow overcomes missing information.
- **report-render (EDGE=100% all arms):** The vague spec is insufficiently ambiguous —
  all edge behaviours (None passthrough, exceptions, column ordering) are natural
  inferences. Not a discriminating task for ambiguity-inference.
- **event-store (test-after=100% vs tdd-no-refactor=0%):** The starkest contrast.
  Writing tests *after* seeing the implementation appears to capture the emergent
  contract more completely. tdd-no-refactor collapses entirely (all CORE fails) —
  jumping to code without a design step produces incoherent implementations under
  vague spec.
- **pricing (test-after=67% vs tdd-refactor=0%):** TDD's red tests anchor on an
  incomplete interpretation of the spec; test-after's post-hoc coverage is more
  comprehensive.

**Mechanism hypothesis:** The finding suggests that under vague spec, TDD's red-test
cycle enforces early commitment to a specific interpretation of the requirements —
which may be the wrong one. Test-after allows the agent to build something working,
then write tests that capture its actual behaviour, producing better EDGE coverage.

---

### changeability verdict: Cumulative changeability

**Primary endpoint 2: Σ blast-radius lines changed across 3-change chain**

| arm | mean Δlines | n cells | vs tdd-refactor |
|-----|-------------|---------|----------------|
| **tdd-refactor** | **664** | 8 | baseline |
| test-after | 700 | 8 | +36 (+5.4%) |
| tdd-no-refactor | 701 | 4 | +37 (+5.6%) |
| bduf | 770 | 4 | +106 (+16%) |

**changeability hypothesis: CONFIRMED.** tdd-refactor has the lowest cumulative blast radius across all
arms and conditions. The advantage is consistent across all 4 tasks (+1% to +12%)
and both clarity conditions (clear: −38 lines; vague: −32 lines).

The bduf penalty is the most striking: +16% more churn than tdd-refactor, driven by
notifier (notifier/bduf/vague mean = 983 lines vs tdd-refactor/clear = 748 lines).

---

### refactoring-vs-ordering verdict: Mechanism isolation (refactoring vs test ordering)

| arm | mean Δlines | condition |
|-----|-------------|-----------|
| tdd-refactor | 664 | clear + vague |
| test-after | 700 | clear + vague |
| tdd-no-refactor | 701 | vague only |

**mechanism-isolation hypothesis: CONFIRMED.** tdd-no-refactor (701) ≈ test-after (700), both substantially
above tdd-refactor (664). Removing the refactoring step from TDD (tdd-no-refactor)
eliminates the changeability advantage — it performs identically to writing tests
after the fact.

This isolates the mechanism: **the benefit of TDD for changeability comes from the
refactoring step, not from test-first ordering**. The red-test alone adds no
changeability value; the green→refactor cycle is the operative step.

Note: tdd-no-refactor/event-store produced 3/3 CORE failures under vague spec
(contributing to the blast-radius average via failed change attempts). Excluding
event-store from tdd-no-refactor still gives ~725 lines vs test-after's ~710 for the
other three tasks — the ordering remains the same.

---

### clarity-interaction verdict: The headline interaction (clarity × workflow)

**Is tdd-refactor's changeability advantage largest under vague spec?**

| clarity | test-after mean | tdd-refactor mean | Δ (ta − tdd) |
|---------|----------------|------------------|--------------|
| clear | 690 | 651 | +39 lines |
| vague | 710 | 678 | +32 lines |

The gap is marginally *larger* under clear spec (+39 lines) than vague spec (+32 lines).
There is no interaction: tdd-refactor's changeability advantage is consistent across
both clarity conditions.

**clarity-interaction hypothesis: NOT CONFIRMED.** The clarity-interaction interaction does not appear for changeability. For
EDGE pass rate, the interaction is reversed from clarity-interaction hypothesis: under clear spec both arms are
equal (100%); under vague spec test-after outperforms tdd-refactor. If anything, the
clarity × workflow interaction favours test-after, not tdd-refactor.

---

### Code and test quality (cross-arm, complete)

| arm | coverage % | test_quality /10 | complexity /10 | avg_cc | avg_mi |
|-----|-----------|-----------------|----------------|--------|--------|
| tdd-refactor | 98.8% | 7.26 | 7.82 | 2.23 | 67.4 |
| tdd-no-refactor | 99.0% | 7.22 | 7.94 | 2.25 | 72.7 |
| test-after | 99.0% | 7.49 | 7.85 | 2.52 | 61.9 |
| bduf | 99.0% | 7.64 | 7.81 | 2.35 | 62.5 |

*Coverage = branch coverage by agent's own tests (before grade files injected).*  
*test_quality, complexity = K=3 multi-rater review scores (0–10), change3 stage.*  
*avg_cc = radon cyclomatic complexity; avg_mi = maintainability index (>65 = maintainable).*

**Observations:**

- Coverage is near-identical across all arms (~99%) — test-first ordering does not
  produce higher self-coverage than test-after.
- test_quality is highest for bduf (7.64) and test-after (7.49), lower for tdd arms
  (7.22–7.26). The differences are small but consistent.
- avg_mi is highest (most maintainable) for tdd-no-refactor (72.7), slightly above
  the 65-threshold. test-after and bduf are below threshold (62). This partially
  contradicts the blast-radius finding — lower MI doesn't translate to lower churn.
- avg_cc is tightly clustered (2.23–2.52); test-after has highest cyclomatic
  complexity despite similar quality scores.

---

### Multi-rater review scores (K=3 passes, complete)

| arm | complexity | naming | performance | structure | test_quality |
|-----|-----------|--------|-------------|-----------|--------------|
| tdd-refactor | 7.82 | 8.76 | 7.46 | 7.50 | 7.26 |
| tdd-no-refactor | 7.94 | 8.70 | 7.67 | 7.56 | 7.22 |
| test-after | 7.85 | 8.79 | 7.71 | 7.62 | 7.49 |
| bduf | 7.81 | 8.67 | 7.56 | 7.67 | 7.64 |

Naming is consistently highest (8.67–8.79) and performance/test_quality lowest
(7.22–7.71) across all arms. The spread between arms is narrow (≤0.4 points) on every
dimension — arms are not meaningfully differentiated by multi-rater review scores.

---

### Cost summary

| arm | mean cost/stage | n stages | total |
|-----|----------------|----------|-------|
| tdd-refactor | $0.44 | 96 | $42.27 |
| bduf | $0.24 | 48 | $11.71 |
| tdd-no-refactor | $0.22 | 48 | $10.74 |
| test-after | **$0.19** | 96 | $17.91 |

tdd-refactor is the most expensive arm (2.3× test-after per stage) due to iterative
test cycles accumulating context across the TDD loop. test-after is the cheapest arm.
The combination of changeability advantage AND higher cost makes tdd-refactor a
deliberate trade-off.

---

## Discussion

### Prior context

The prior experiment line ([`01-final-results.md`](01-final-results.md), which
subsumes an earlier two-arm TDD-vs-test-after cut of the same data) found **no significant advantage
for test-first** across a range of task sizes. Both studies used clear specs and
single-shot tasks with no change chain — precisely the conditions where TDD's claimed
benefits (ambiguity resolution and design improvement under feedback) are absent.

This experiment adds both missing conditions simultaneously: vague specs that leave
real decisions unstated, and a multi-stage change chain that punishes rigid designs.

### Summary of verdicts

| Hypothesis | Direction | Result |
|------------|-----------|--------|
| ambiguity hypothesis: TDD passes more EDGE under vague | tdd-refactor > test-after | **REJECTED — reversed** (test-after 67% vs tdd-refactor 33%) |
| changeability hypothesis: TDD has lower cumulative blast radius | tdd-refactor < all others | **CONFIRMED** (664 vs 700–770) |
| mechanism-isolation hypothesis: Refactoring is the mechanism | tdd-no-refactor ≈ test-after | **CONFIRMED** (701 vs 700) |
| clarity-interaction hypothesis: Advantage largest under vague | gap larger at vague | **NOT CONFIRMED** (gap similar, slightly larger at clear) |

### The ambiguity hypothesis reversal: why test-after wins on EDGE under vague spec

The pre-registered hypothesis assumed that TDD's red-test cycle would force explicit
edge-case decisions early, producing better contract inference under ambiguity.
The data shows the opposite: writing tests *after* building a working system
produces higher EDGE pass rates under vague spec.

**The most important finding first — vague requirements are a communication problem,
not a technical one.** The notifier task makes this unavoidable: its vague spec omitted
per-channel retry semantics that are not inferrable from context. Every workflow —
TDD, test-after, BDUF — scored 0% EDGE. No methodology compensates for information
that was never stated. The correct response to a vague spec is a conversation with the
stakeholder, not a choice of coding workflow.

For the ambiguities that *are* recoverable from context (pricing, event-store), two
mechanisms explain why test-after outperforms TDD:

1. **Anchoring effect:** TDD's red tests commit to a specific interpretation of the
   vague spec before any implementation feedback is available. That commitment may be
   systematically incomplete — missing the edge decisions the EDGE tests care about.
   test-after sees a full working implementation first, then writes tests that capture
   its actual behaviour, including emergent edge handling that the spec didn't specify.

2. **Spec-gap vs workflow-gap:** The notifier result (0% EDGE for all arms) establishes
   a ceiling: some ambiguities are irreducible. The event-store and pricing results
   show that where information IS recoverable from context, test-after recovers more of
   it. TDD's anchoring effect is a liability exactly where you'd hope it would help.

The tdd-no-refactor arm provides a further clue: it collapses entirely on event-store
(0/3 CORE, 0/3 change stages), while test-after passes 3/3. Both arms write tests,
but tdd-no-refactor writes them *before* seeing a working system — and under a vague
spec, those early tests do not constrain the design enough to produce a valid
implementation. The order of seeing-code-then-writing-tests appears protective.

### The changeability hypothesis/mechanism-isolation hypothesis result: refactoring is the changeability driver

tdd-no-refactor (701) ≈ test-after (700) > tdd-refactor (664) confirms that the
green→refactor cycle — not test-first ordering — drives the changeability advantage.
This replicates the changeability hypothesis finding from the prior studies while adding the mechanistic
isolation that those studies could not provide.

The practical implication: teams who do test-first without disciplined refactoring get
the cost premium of TDD (2.3× per stage) with none of the changeability benefit. The
refactoring step is load-bearing.

### Design trap calibration

**Pricing** (trap: change2, category-scoped discounts):

- Naive: single-pass loop applying each discount to global subtotal — must scan all
  items with category filter for change2.
- Clean: `Discount.compute_savings(items, current_total)` — change2 is a 2-line change.

**Notifier** (trap: change2, per-channel retry):

- Naive: flat `send()` loop with `handler(msg)` calls — retry state requires a
  `register_channel` signature change.
- Clean: per-channel dict with `{"handler": fn, "max_retries": 0, ...}` — retry is
  a 1-line change to `register_channel`.

**Report-render** (trap: change3, streaming `render_stream()`):

- Naive: `render()` returns `handler(data)` directly as string — streaming requires
  restructuring the dispatch.
- Clean: registry maps format to `{"handler": fn}` — `render_stream()` wraps with
  `yield` without touching `render()`.

**Event-store** (trap: change3, projection snapshots):

- Naive: flat global list of all events — `project()` always scans from the start.
- Clean: per-stream dict `{stream_id: [events]}` — snapshot is a 3-line addition.

Key calibration result: all trap changes absorbed efficiently in tdd-refactor/clear
(clear spec + refactored codebase = minimal trap penalty). The trap signal is largest
in vague-spec cells with less disciplined design.

### Vagueness calibration

The vague specs were authored to omit architecture guidance and edge-case decisions
without making the task impossible. Expected profile: CORE ~100%, EDGE 50–80%.

Actual profile diverged:

- report-render: EDGE ~100% (spec leaked enough to always infer EDGE) — weak discriminator
- notifier: EDGE ~0% (spec too sparse to infer retry semantics) — discriminator floor

The informative range was pricing and event-store (EDGE 0–100% depending on arm),
which provided the cleanest ambiguity-inference signal.

---

## Limitations

1. **n = 3 per cell (pre-registered).** Small for parametric tests. Verdicts use
   sign tests and direction of pooled means across tasks; effect sizes should be
   replicated at higher N before drawing strong conclusions.
2. **Single model, single temperature.** Results may not generalise across models.
   The prior studies used the same `claude-sonnet-4-6` model, which is a strength
   for comparability but a limitation for generalisability.
3. **Autonomous-only.** No human-in-the-loop, no clarification oracle. Real TDD
   practitioners use the red test to prompt a conversation. The experiment measures
   what the workflow *structure* alone produces.
4. **Reviewer variance.** Multi-rater review uses the same model with K=3 passes.
   LLM reviewer variance can be high; the deterministic blast-radius and EDGE counts
   are primary. Review scores are secondary.
5. **report-render weak EDGE calibration.** All arms pass EDGE regardless of
   clarity condition — this task is not ambiguity-inference-informative. Its trap signal
   (change3 blast radius) is present but weaker than notifier.
6. **notifier as a spec-gap floor.** All arms fail EDGE under vague for notifier.
   This limits ambiguity-inference signal to 2 of 4 tasks (pricing, event-store) — still directionally
   consistent but narrows the evidence base.
7. **Two contaminated trials (high_turn_count).** pricing/tdd-refactor/clear t3
   (turns=40) and pricing/tdd-refactor/vague t3 (turns=43) hit the turn limit.
   Both flagged `contamination: high_turn_count`; their change stages completed and
   are included in blast-radius totals.

---

## Recommendation

### On vague requirements: this is a communication problem

The notifier result is the clearest finding in the entire dataset: when the spec omits
information that is not inferrable from context, every workflow scores 0% on the
behavioural assertions that depend on it. TDD, test-after, and BDUF are indistinguishable
at the floor. **No coding methodology compensates for information that was never stated.**

The practical response to a vague spec is not a workflow choice — it is a conversation.
Before building, identify what the spec leaves unstated and ask. The cost of a
clarifying question is minutes; the cost of building the wrong contract is discovered
later, and measured in the blast-radius numbers in this report.

For the ambiguities that *are* contextually recoverable, test-after (67% EDGE under
vague) outperforms TDD (33%) because it defers commitment until after a working
implementation exists. The workflow that follows from the data:

1. Identify what is missing from the spec and ask the stakeholder
2. Build something working
3. Write tests against what you built — not what you imagined
4. Show the test contract to the stakeholder as a precise statement of assumed behaviour

This surfaces decisions that were implicit and turns them into an explicit conversation,
which is what the spec should have contained in the first place.

### On changeability: TDD with refactoring works, but only the refactoring step matters

**For long-lived codebases with expected changes:** Use TDD with disciplined refactoring.
The blast-radius advantage (~5–12% fewer lines across a 3-change chain) is consistent
across all 4 tasks and both clarity conditions. It compounds with code longevity.

**The refactoring step is load-bearing.** tdd-no-refactor (701 mean Δlines) ≈ test-after
(700) — removing the green→refactor cycle eliminates the changeability advantage entirely.
Teams doing test-first without disciplined refactoring pay the cost premium of TDD
(2.3× per stage) with none of the benefit.

### Cost-adjusted decision guide

| Situation | Recommended workflow | Why |
|-----------|---------------------|-----|
| Vague requirements | **Clarify first, then test-after** | No workflow beats a conversation; test-after then captures the contract you actually built |
| Clear requirements, long-lived codebase | **TDD with refactoring** | −5–12% blast radius over a change chain |
| Clear requirements, one-shot delivery | **test-after** | Same quality, 2.3× cheaper than TDD |
| Speed-first / throwaway | **test-after or tdd-no-refactor** | Same changeability as each other, lower cost |

**What this adds to the prior null results:** The prior two studies found no TDD
advantage under clear specs with no change chain. This experiment confirms the advantage
is real — but only for changeability under a change chain, not for ambiguity resolution.
TDD pays off, but not for the reason most commonly claimed, and only when the refactoring
step is taken seriously.

---

*Report generated by `claude-sonnet-4-6` in a remote Claude Code session.*  
*Raw data: [`docs/experiments/data/`](data/)*  
*Analysis script: [`scripts/analyze_tdd_pays.py`](../../scripts/analyze_tdd_pays.py)*

---

## Second Run: spec-synthesis and test-after-refactor (pre-registration)

**Pre-registration timestamp:** 2026-06-24 (before any second-run data collected)

The first run could not answer two questions because the relevant arms were missing:

- **spec-synthesis:** Does the `ship` arm's explicit acceptance-criteria synthesis (`/specs`→`/plan`→`/build`) resolve ambiguity as well as or better than `tdd-refactor`'s failing-test-as-specification approach?
- **test-after-refactor:** Does `test-after-refactor` (code → tests against working impl → refactor) dominate all existing arms simultaneously on EDGE pass rate, blast radius, and cost?

### Second-run pre-registration

| Item | Value |
|------|-------|
| N per new cell | 3 trials (same as first run) |
| New primary: test-after-refactor Condition 1 | EDGE under vague: test-after-refactor ≥ test-after (−5 pp tolerance) |
| New primary: test-after-refactor Condition 2 | Cumulative blast radius: test-after-refactor within 10% of tdd-refactor |
| New primary: test-after-refactor Condition 3 | Cost/stage: test-after-refactor < tdd-refactor |
| New primary: spec-synthesis | ship EDGE under vague ≥ tdd-refactor EDGE under vague |

**spec-synthesis hypothesis:** under `vague`, `ship` EDGE pass rate ≥ `tdd-refactor` because `/specs` forces the agent to state every acceptance decision before any code is written. Null: `/specs` makes the same happy-path assumptions as any other arm — spec synthesis from a vague prompt does not reliably surface EDGE decisions.

**dominance hypothesis:** `test-after-refactor` dominates every existing arm simultaneously: EDGE ≥ `test-after` (deferred tests capture actual contract), blast radius ≈ `tdd-refactor` (refactoring under tests provides same structural safety net), cost < `tdd-refactor` (no iterative red-green cycles during initial build). All three conditions must hold. Null: the refactor phase changes the implementation enough that post-refactor tests diverge, or the iterative TDD cycle shapes design in ways a post-implementation refactor cannot replicate.

### Second-run design matrix

| | tdd-refactor | tdd-no-refactor | test-after | test-after-refactor | bduf | ship |
|---|---|---|---|---|---|---|
| **clear** | ✓ (first run) | – | ✓ (first run) | ✓ **new** | – | – |
| **vague** | ✓ (first run) | ✓ (first run) | ✓ (first run) | ✓ **new** | ✓ (first run) | ✓ **new** |

3 new arm-clarity cells × 4 tasks × 3 trials = **36 new cells**, 144 new dispatches.

### Execution commands (second run)

```bash
# Precondition for 'ship' arm: build a plugin-enabled HOME template once
TPL=/tmp/ship-template
mkdir -p $TPL
cp -r ~/.claude/plugins $TPL/.claude  # or wherever plugins live

# Run only the new second-run cells (test-after-refactor + ship)
for TASK in pricing notifier report-render event-store; do
  python3 scripts/run_tdd_pays_experiment.py \
    --only "exp-tdd-pays-${TASK}" \
    --clarity second \
    --trials 3 \
    --model claude-sonnet-4-6 \
    --ship-home-template $TPL \
    --out "docs/experiments/data/tdd-pays-${TASK}-run2-2026-06-24.jsonl" \
    --run-root "/tmp/tdd-pays-${TASK}-run2" &
done
wait
```

Combined analysis across both runs:

```bash
python3 scripts/analyze_tdd_pays.py \
  --data \
    docs/experiments/data/tdd-pays-*-2026-06-23.jsonl \
    docs/experiments/data/tdd-pays-*-run2-2026-06-24.jsonl \
  --out /tmp/combined-analysis.md
```

### Predicted outcomes (to be updated with actuals)

Based on the first-run evidence (see experiment document, "Best path forward" section):

| Metric | Predicted |
|--------|-----------|
| test-after-refactor EDGE / vague | ~67% (matching test-after) — deferred tests survive refactor |
| test-after-refactor blast radius | ~664 (matching tdd-refactor) — refactoring under tests provides same structural benefit |
| test-after-refactor cost/stage | ~$0.25–0.30 (between test-after $0.19 and tdd-refactor $0.44) |
| ship EDGE / vague | ≥ tdd-refactor (33%) — explicit spec synthesis forces unstated decisions |
| ship changeability | ≤ tdd-refactor (664) — inline review checkpoints in /build catch structural issues |

**dominance hypothesis falsification criteria:** If test-after-refactor blast radius exceeds tdd-refactor by ≥10%, the iterative TDD cycle shapes design in ways a post-implementation refactor cannot replicate, and tdd-refactor remains the correct choice for open-design tasks despite its higher cost.

---

## Second-Run Results (2026-06-24)

**Data:** `docs/experiments/data/tdd-pays-*-run2-2026-06-24.jsonl`  
**Combined analysis across 465 rows (first + second run).**

### spec-synthesis: Ship arm vs tdd-refactor

**Hypothesis spec-synthesis hypothesis:** `ship` EDGE pass rate under vague ≥ `tdd-refactor`

> **Execution note (2026-06-24).** The automated harness recorded every `ship` trial
> as a 900-second CCR dispatch timeout, leaving only synthesized-failure placeholder
> rows (all CORE/EDGE = 0%). The `ship` arm was therefore **re-run manually with no
> dispatch timeout**: 4 tasks × 3 trials × (stage0 + 3 changes) = 48 graded stages,
> each a full autonomous `/specs`→`/plan`→`/build` pipeline on the vague spec, with the
> CORE/EDGE graders sealed (copied and executed, never read) until each stage was
> frozen. The timeout placeholders have been replaced in the run2 data by these real
> results. The manual run captured CORE/EDGE pass-fail only — not blast radius or cost.

| task | ship EDGE | tdd-refactor EDGE | Δ |
|------|-----------|------------------|---|
| exp-tdd-pays-event-store | 0% (n=3) | 33% (n=3) | −33 pp |
| exp-tdd-pays-notifier | 0% (n=3) | 0% (n=3) | 0 pp |
| exp-tdd-pays-pricing | 0% (n=3) | 0% (n=3) | 0 pp |
| exp-tdd-pays-report-render | 100% (n=3) | 100% (n=3) | 0 pp |

**Pooled EDGE: ship 25% (3/12) vs tdd-refactor 33% (4/12)**

**Verdict: spec-synthesis hypothesis REJECTED (null supported).** Run to completion, the `ship` pipeline's
explicit `/specs` acceptance-criteria synthesis did **not** surface omitted edge
decisions better than `tdd-refactor`'s failing-test-as-specification approach — 25% vs
33% pooled EDGE, with ship matching or trailing tdd-refactor on every task. The
pre-registered null holds: `/specs` makes the same happy-path assumptions as any other
arm and does not reliably surface EDGE decisions from a vague prompt.

**Mechanism (from the agents' own acceptance criteria).** Each trial saved the `/specs`
document it generated. These criteria enumerated many ambiguities but resolved them to
**happy-path defaults**. `/specs` landed on the correct edge behaviour only for
report-render — the one task whose omitted decisions (insertion-order iteration,
by-reference returns) *are* the natural defaults — and either omitted or explicitly
mis-resolved them for pricing (discount priority / exclusive groups), notifier
(per-channel priority, exception-as-False), and event-store (optimistic-concurrency
trigger, `initial_state`). Writing acceptance criteria from a vague prompt does not, by
itself, force the unstated decisions into view; it produces a confident-looking spec
built on the same assumptions a happy-path implementation makes.

**What the ship workflow produces.** The `ship` arm runs the dev-team pipeline end to
end, self-approving at each gate. `/specs` first turns the vague `spec.md` into an
explicit specification — an intent description, an architecture spec, numbered
GIVEN/WHEN/THEN acceptance criteria, an **"explicit decisions on omitted behaviors"**
table, and a self-checked **consistency gate** — then `/plan` decomposes it into an
incremental TDD plan, and `/build` implements it RED-GREEN-REFACTOR. Every trial emitted
these artifacts (a 54–145-line `ACCEPTANCE.md` plus per-stage plan files), and the
pipeline ran to completion on all 48 stages with no human input.

Those artifacts show *why* the EDGE scores came out flat: `/specs` does drag the omitted
decisions onto the page, but it then resolves them to the happy path and certifies the
result complete. The event-store spec is the clearest case — it listed the trap
decisions explicitly and chose the wrong side of both:

> **D1** — `OptimisticConcurrencyError` usage … `append` does **not** take
> `expected_version` in this version
> **D5** — `project` initial state … always starts at `None`; not configurable

…then stamped **"Consistency Gate: PASS — every behavior maps to an acceptance
criterion."** Both decisions are the exact opposite of what `acc_core.py` requires (an
`expected_version` conflict *must* raise `OptimisticConcurrencyError`; `project(…,
initial_state=…)` *must* be honoured). So the failure is not an oversight the process
forgot to consider — `/specs` surfaced the decision, reasoned about it, committed to the
wrong default, and signed off. A self-authored spec from a vague prompt manufactures
false confidence: it reads as thorough and internally consistent while encoding the same
assumptions a happy-path implementation would have made silently. That is the core spec-synthesis
result — explicit spec synthesis relocates the guess from the code to the spec; it does
not eliminate it.

**CORE and changeability.** ship CORE under vague was 100% for pricing, notifier, and
report-render but **0% for event-store** — that task's `acc_core.py` encodes the
optimistic-concurrency and `initial_state` behaviours as *core* (not edge) acceptance,
so failing to surface them fails CORE outright (the agents' own suites passed while the
hidden acceptance failed — the "looks done, isn't" signal). Across the change chain ship
kept CORE green for those three tasks and the change-specific graders passed 33/36;
event-store stayed at 0% throughout. **spec-synthesis2 (changeability) is not measured** in this
manual run — blast radius and cost were not captured, so the analyzer's "ship blast
radius 0" is an artifact of the absent fields, not a real zero.

**Practical implication.** The earlier "ship is too slow for the dispatch budget" caveat
was an environment artifact, not a property of the method. Run to completion, the
`/specs`→`/plan`→`/build` pipeline is fully comparable to the other arms on contract
inference — and on this benchmark it does not beat them. Explicit up-front spec synthesis
is not a substitute for clarifying a vague spec with the stakeholder.

---

### test-after-refactor: test-after-refactor dominance

**Hypothesis dominance hypothesis:** `test-after-refactor` dominates all existing arms simultaneously on EDGE pass rate (≥ test-after), blast radius (within 10% of tdd-refactor), and cost (< tdd-refactor). All three conditions must hold.

#### Condition 1: EDGE pass rate under vague (test-after-refactor ≥ test-after, −5 pp tolerance)

| task | test-after-refactor EDGE | test-after EDGE | tdd-refactor EDGE | Condition 1 |
|------|--------------------------|-----------------|------------------|-------------|
| exp-tdd-pays-event-store | 0% (n=3) | 100% (n=3) | 33% (n=3) | ✗ (−100 pp) |
| exp-tdd-pays-notifier | 0% (n=4) | 0% (n=3) | 0% (n=3) | ✓ (0 pp) |
| exp-tdd-pays-pricing | 0% (n=6) | 67% (n=3) | 0% (n=3) | ✗ (−67 pp) |
| exp-tdd-pays-report-render | 0% (n=3) | 100% (n=3) | 100% (n=3) | ✗ (−100 pp) |

**Pooled: test-after-refactor 0% vs test-after 67% → Condition 1 FAILS**

The `test-after-refactor` arm under vague spec produced 0% EDGE pass rate across 3 of 4 tasks. The refactor phase appears to remove or rewrite the edge-case-covering tests that were written against the working implementation, leaving the final suite less comprehensive than unrefactored `test-after`.

#### Condition 2: Blast radius within 10% of tdd-refactor

| arm | mean Δlines | vs tdd-refactor | Condition 2 |
|-----|-------------|-----------------|-------------|
| test-after-refactor | 678 | +2.1% | ✓ |
| tdd-refactor | 664 | — | — |
| test-after | 700 | +5.4% | — |

**Condition 2 HOLDS** — test-after-refactor blast radius (678 lines) is within 2.1% of tdd-refactor (664 lines), well inside the 10% tolerance.

**Clarification — the two refactor arms are equivalent on changeability, and that is
*consistent* with "refactoring is the mechanism," not a contradiction of it.** It is
tempting to read tdd-refactor (664) < test-after-refactor (678) as "test-first ordering
buys extra changeability on top of refactoring." The data does not support that reading.
The 14-line gap is +2.1% — inside the 10% tolerance and, at n=3 per cell, inside the
noise. The robust, consistent signal in this dataset is **refactor vs no-refactor**, not
TDD vs test-after:

| | refactor step | mean Δlines |
|---|---|---|
| tdd-refactor | yes | 664 |
| test-after-refactor | yes | 678 |
| test-after | no | 700 |
| tdd-no-refactor | no | 701 |

Both refactor arms (664, 678) sit ~5–6% below both non-refactor arms (700, 701), and
adding a refactor pass to test-after moved it 700 → 678, into the same band as
tdd-refactor. Test-first ordering does not separate from test-after *once both refactor*.
The headline mechanism-isolation hypothesis finding — the green→refactor cycle, not test ordering, drives
changeability — holds, and the refactor-arm tie is a second confirmation of it.

The residual 14 lines, *if* it is real rather than noise, has two candidate explanations,
neither established by this experiment:

1. **Refactoring granularity.** tdd-refactor refactors in small steps on every green, so
   cleanup tracks the design as it grows; test-after-refactor does one cleanup pass after
   the whole component is built. A late lump-sum refactor may have less leverage than many
   incremental ones.
2. **Safety-net erosion.** test-after-refactor's refactor phase rewrites or deletes its
   own tests (the same effect that collapsed its EDGE coverage to 0% under vague spec,
   Condition 1). A churned test suite is a weaker safety net when the three follow-up
   changes land, which could nudge later blast radius up.

Distinguishing "real but small effect" from "noise," and adjudicating between these two
mechanisms, requires a dedicated higher-power experiment — see
[Proposed follow-up: refactoring cadence](#proposed-follow-up-refactoring-cadence-and-the-test-safety-net).

#### Condition 3: Cost per stage < tdd-refactor

| arm | mean cost/stage |
|-----|----------------|
| test-after | $0.19 |
| tdd-no-refactor | $0.22 |
| bduf | $0.24 |
| test-after-refactor | $0.35 |
| tdd-refactor | $0.44 |

**Condition 3 HOLDS** — test-after-refactor ($0.35/stage) is 20% cheaper than tdd-refactor ($0.44/stage).

#### dominance hypothesis Overall Verdict

**dominance hypothesis NOT SUPPORTED.** Condition 1 fails decisively: under a vague spec, `test-after-refactor` produces 0% EDGE pass rate (pooled across 3 of 4 tasks), worse than both `test-after` (67%) and `tdd-refactor` (33%). The refactoring phase degrades edge-case coverage when the spec is ambiguous — the agent refactors away the tests that document its own decisions.

Conditions 2 and 3 both hold: the blast radius is equivalent to tdd-refactor (+2.1%) and the cost is 20% lower. But the EDGE failure dominates.

**The mechanism:** Under vague spec, `test-after-refactor` suffers from an ordering problem that `test-after` avoids. In `test-after`, tests written against the working implementation capture the agent's edge-case choices and stay in place. In `test-after-refactor`, those tests are then exposed to a refactor phase that rewrites the implementation — the agent often also rewrites or removes tests it considers redundant, stripping out the documented edge-case decisions. The result is structurally clean code with no EDGE coverage.

**Revised decision guide (incorporating second-run results):**

| Situation | Recommended workflow |
|-----------|---------------------|
| Vague requirements | **Stop and clarify first.** No workflow recovers omitted decisions — including agentic spec synthesis: `ship`'s `/specs` scored 25% EDGE under vague, no better than tdd-refactor (33%). |
| Clear requirements, long-lived codebase | **tdd-refactor** (lowest blast radius, best structural benefit) |
| Clear requirements, one-shot or cost-sensitive | **test-after** (same EDGE quality as tdd-refactor under clear spec, 2.3× cheaper) |
| Want refactoring benefits without TDD overhead | **test-after-refactor** (clear spec only — vague spec destroys edge-case coverage during refactor) |
| Speed-first, throwaway code | **tdd-no-refactor or test-after** (same changeability, lowest cost) |

---

## Proposed follow-up: refactoring cadence and the test safety net

**Status: proposed, not yet run.** Pre-registration drafted; no data collected.

The second run left one question open (see the
[Condition 2 clarification](#condition-2-blast-radius-within-10-of-tdd-refactor)).
tdd-refactor (664) and test-after-refactor (678) are statistically equivalent on
changeability at n=3 — the 14-line gap is inside the noise. Two questions remain:

1. **Is the gap real at all,** or does it vanish under adequate statistical power?
2. **If real, which mechanism produces it** — refactoring *granularity* (many small
   in-loop refactors vs one post-hoc pass) or *safety-net erosion* (the one-shot refactor
   churning its own test suite)?

### Hypotheses (to pre-register before any data)

- **equivalence hypothesis:** continuous-refactor and one-shot-refactor workflows are
  equivalent on cumulative blast radius within a ±5% margin (TOST). This is the default
  the second-run data points to; the experiment is powered to *reject* it if a real
  effect exists.
- **granularity hypothesis:** holding the test-protection factor constant, **continuous**
  refactoring yields lower blast radius than **one-shot** refactoring. Predicts the gap
  survives even when tests are protected from churn.
- **safety-net hypothesis:** **freezing the test suite during the refactor** raises EDGE pass
  rate (tests that document edge decisions survive) and lowers subsequent blast radius
  relative to a free refactor. Predicts test-suite churn *mediates* the blast-radius
  difference.

granularity hypothesis and safety-net hypothesis are not mutually exclusive; the design separates their contributions.

### Design — a 2×2, adequately powered

Cross **refactor granularity** × **test protection during refactor**, with tdd-refactor
as an external reference:

| | tests free to change in refactor | tests frozen during refactor |
|---|---|---|
| **one-shot refactor** (single pass after build) | test-after-refactor *(current arm)* | test-after-refactor-frozen |
| **continuous refactor** (refactor each increment) | test-after-continuous | test-after-continuous-frozen |

Plus **tdd-refactor** (continuous, test-first) as the reference point from the prior runs.
Reuse the same 4 tasks, vague **and** clear spec, 3-change chain.

**Power.** The n=3 cells could not resolve a 2% effect. Estimate the per-cell blast-radius
SD from the existing run1+run2 data, then size n for 80% power to detect a 5% difference
(and to make the ±5% TOST equivalence test meaningful). Expect this to require roughly
**n = 12–15 per cell** rather than 3; pre-register the exact n from the power calc.

**Instrumentation (new, per stage).** The current harness records blast radius and
pass-rates; add:

- **refactor granularity (actual):** count of distinct refactor edits between first-green
  and stage-complete — verifies the assigned arm behaved as intended.
- **test-suite churn during refactor:** test LOC added + deleted between first-green and
  post-refactor. This is the mediator variable for safety-net hypothesis.
- carry forward CORE/EDGE pass rates and cost/stage.

### Analysis plan (pre-registered)

- **Headline:** TOST equivalence test on cumulative blast radius, continuous vs one-shot,
  ±5% margin → resolves question 1 (real vs noise) directly, including a "confirmed
  equivalent" outcome as a valid result.
- **granularity hypothesis:** two-factor model on blast radius; granularity main effect with test-protection
  held constant.
- **safety-net hypothesis:** mediation — does test-suite churn account for the granularity/protection effect
  on blast radius? Plus the direct EDGE comparison frozen vs free (this also re-tests the
  test-after-refactor Condition 1 finding that free refactor destroys edge coverage under vague spec).

### What each outcome would mean

| Result | Interpretation |
|---|---|
| TOST confirms equivalence | The refactor-arm tie is real; "refactoring is the mechanism" is the whole story, and *how* you refactor (granularity, ordering) does not move changeability. Strongest, simplest takeaway. |
| Granularity effect, no churn mediation | Continuous refactoring is independently better; recommend refactoring in small steps regardless of test ordering. |
| Churn mediation (safety-net hypothesis) | The cost of one-shot refactor is collateral test-suite damage; recommend protecting/regenerating the test suite across a refactor, and the test-after-refactor EDGE collapse and the changeability residual share one root cause. |

A null here is a publishable result: confirming that the two refactor workflows are
genuinely interchangeable on changeability would let teams choose between them on the axes
that *did* separate cleanly — cost and edge-case robustness under vague specs.
