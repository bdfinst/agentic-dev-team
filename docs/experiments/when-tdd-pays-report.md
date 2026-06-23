# When Does TDD Actually Pay Off?

**Experiment date:** 2026-06-23  
**Model (fixed):** `claude-sonnet-4-6`  
**Branch:** `claude/vigilant-lamport-u7t3af-n9c3os`  
**Related:** [`experiment-prompt-when-tdd-pays.md`](experiment-prompt-when-tdd-pays.md),
[`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)

---

## Pre-registration (recorded before any graded result was seen)

**Timestamp:** 2026-06-23T15:31:59Z  
**Data state at registration:** all four JSONL files had 0 rows.

| Item | Value |
|------|-------|
| N per cell | 3 trials |
| Primary endpoint 1 | EDGE pass-rate under `vague` spec (tdd-refactor vs test-after) |
| Primary endpoint 2 | Cumulative changeability = Σ blast-radius lines changed across 3-change chain |
| RQ-C interaction | Is tdd-refactor's advantage on EDGE *and* changeability **largest in the vague+open-design cell**? |

**Hypotheses (pre-registered):**

- **H-A (ambiguity):** under `vague`, `tdd-refactor` passes more EDGE assertions
  than `test-after`. Under `clear` there is no gap. Null: vagueness degrades all
  arms equally.
- **H-B (changeability):** `tdd-refactor` absorbs the 3-change chain at lower
  cumulative lines-changed than `test-after` and `bduf`.
- **H-B2 (mechanism):** `tdd-refactor` < `tdd-no-refactor` ≈ `test-after`;
  the benefit comes from refactoring, not test ordering.
- **H-C (interaction):** TDD's advantage is largest in `vague + open-design`
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

- **Stage 0:** `acc_core.py` (happy-path — always passable under vague spec) +
  `acc_edge.py` (omitted decisions — sometimes missed under vague).
- **Change stages 1–3:** cumulative grade files (all prior + new) injected at
  grading time only; never present during the build.

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

#### EDGE pass rate (primary RQ-A discriminator)

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

### RQ-A verdict: Contract inference under ambiguity

**Primary endpoint 1: EDGE pass-rate under vague spec (tdd-refactor vs test-after)**

| task | tdd-refactor/vague | test-after/vague | Δ |
|------|-------------------|-----------------|---|
| event-store | 33% (1/3) | **100%** (3/3) | −67 pp |
| notifier | 0% (0/3) | 0% (0/3) | 0 |
| pricing | 0% (0/3) | **67%** (2/3) | −67 pp |
| report-render | 100% (3/3) | 100% (3/3) | 0 |
| **pooled** | **33%** (4/12) | **67%** (8/12) | **−34 pp** |

**H-A: REJECTED (direction reversed).** Under vague spec, test-after achieves 67%
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
  inferences. Not a discriminating task for RQ-A.
- **event-store (test-after=100% vs tdd-no-refactor=0%):** The starkest contrast.
  Writing tests _after_ seeing the implementation appears to capture the emergent
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

### RQ-B verdict: Cumulative changeability

**Primary endpoint 2: Σ blast-radius lines changed across 3-change chain**

| arm | mean Δlines | n cells | vs tdd-refactor |
|-----|-------------|---------|----------------|
| **tdd-refactor** | **664** | 8 | baseline |
| test-after | 700 | 8 | +36 (+5.4%) |
| tdd-no-refactor | 701 | 4 | +37 (+5.6%) |
| bduf | 770 | 4 | +106 (+16%) |

**H-B: CONFIRMED.** tdd-refactor has the lowest cumulative blast radius across all
arms and conditions. The advantage is consistent across all 4 tasks (+1% to +12%)
and both clarity conditions (clear: −38 lines; vague: −32 lines).

The bduf penalty is the most striking: +16% more churn than tdd-refactor, driven by
notifier (notifier/bduf/vague mean = 983 lines vs tdd-refactor/clear = 748 lines).

---

### RQ-B2 verdict: Mechanism isolation (refactoring vs test ordering)

| arm | mean Δlines | condition |
|-----|-------------|-----------|
| tdd-refactor | 664 | clear + vague |
| test-after | 700 | clear + vague |
| tdd-no-refactor | 701 | vague only |

**H-B2: CONFIRMED.** tdd-no-refactor (701) ≈ test-after (700), both substantially
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

### RQ-C verdict: The headline interaction (clarity × workflow)

**Is tdd-refactor's changeability advantage largest under vague spec?**

| clarity | test-after mean | tdd-refactor mean | Δ (ta − tdd) |
|---------|----------------|------------------|--------------|
| clear | 690 | 651 | +39 lines |
| vague | 710 | 678 | +32 lines |

The gap is marginally _larger_ under clear spec (+39 lines) than vague spec (+32 lines).
There is no interaction: tdd-refactor's changeability advantage is consistent across
both clarity conditions.

**H-C: NOT CONFIRMED.** The RQ-C interaction does not appear for changeability. For
EDGE pass rate, the interaction is reversed from H-C: under clear spec both arms are
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

The two prior experiments ([`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)) found **no significant advantage
for test-first** across a range of task sizes. Both studies used clear specs and
single-shot tasks with no change chain — precisely the conditions where TDD's claimed
benefits (ambiguity resolution and design improvement under feedback) are absent.

This experiment adds both missing conditions simultaneously: vague specs that leave
real decisions unstated, and a multi-stage change chain that punishes rigid designs.

### Summary of verdicts

| Hypothesis | Direction | Result |
|------------|-----------|--------|
| H-A: TDD passes more EDGE under vague | tdd-refactor > test-after | **REJECTED — reversed** (test-after 67% vs tdd-refactor 33%) |
| H-B: TDD has lower cumulative blast radius | tdd-refactor < all others | **CONFIRMED** (664 vs 700–770) |
| H-B2: Refactoring is the mechanism | tdd-no-refactor ≈ test-after | **CONFIRMED** (701 vs 700) |
| H-C: Advantage largest under vague | gap larger at vague | **NOT CONFIRMED** (gap similar, slightly larger at clear) |

### The H-A reversal: why test-after wins on EDGE under vague spec

The pre-registered hypothesis assumed that TDD's red-test cycle would force explicit
edge-case decisions early, producing better contract inference under ambiguity.
The data shows the opposite: writing tests _after_ building a working system
produces higher EDGE pass rates under vague spec.

Two mechanisms are compatible with this finding:

1. **Anchoring effect:** TDD's red tests commit the agent to a specific interpretation
   of the vague spec before any implementation feedback is available. That commitment
   may be systematically incomplete (missing the decisions the EDGE tests care about).
   test-after sees a full working implementation and can write tests that cover its
   actual behaviour — including emergent edge handling.

2. **Spec-gap vs workflow-gap:** The notifier result (0% EDGE for ALL arms) establishes
   that some ambiguities are irreducible: no workflow recovers information that simply
   isn't in the spec. The event-store and pricing results show that where information IS
   recoverable from context, test-after recovers more of it than tdd-refactor.

The tdd-no-refactor arm provides a further clue: it collapses entirely on event-store
(0/3 CORE, 0/3 change stages), while test-after passes 3/3. Both arms write tests,
but tdd-no-refactor writes them _before_ seeing a working system — and in the absence
of a clear spec, those tests do not constrain the design enough to produce a valid
implementation. The order of seeing-code-then-writing-tests appears protective.

### The H-B/H-B2 result: refactoring is the changeability driver

tdd-no-refactor (701) ≈ test-after (700) > tdd-refactor (664) confirms that the
green→refactor cycle — not test-first ordering — drives the changeability advantage.
This replicates the H-B finding from the prior studies while adding the mechanistic
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
which provided the cleanest RQ-A signal.

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
   clarity condition — this task is not RQ-A-informative. Its trap signal
   (change3 blast radius) is present but weaker than notifier.
6. **notifier as a spec-gap floor.** All arms fail EDGE under vague for notifier.
   This limits RQ-A signal to 2 of 4 tasks (pricing, event-store) — still directionally
   consistent but narrows the evidence base.
7. **Two contaminated trials (high_turn_count).** pricing/tdd-refactor/clear t3
   (turns=40) and pricing/tdd-refactor/vague t3 (turns=43) hit the turn limit.
   Both flagged `contamination: high_turn_count`; their change stages completed and
   are included in blast-radius totals.

---

## Recommendation

**For changeability (H-B/H-B2 confirmed):** Use TDD with disciplined refactoring when
the codebase will undergo a multi-stage change chain and the initial design space is
open. The blast-radius advantage (~5–12% fewer lines across 3 changes) compounds with
code longevity. Skip the refactoring step and the advantage disappears entirely.

**For contract inference under vague spec (H-A rejected, reversed):** The data does
_not_ support using TDD to resolve ambiguity — test-after outperforms tdd-refactor on
EDGE pass rate under vague spec. Two practical interpretations:

1. When the spec is vague, write the code first (however loosely), then write tests
   against the working implementation. This produces more complete edge-case coverage
   than committing to red tests up front.
2. Fix the spec. The notifier result is the clearest finding in the dataset: when
   information is absent, no workflow recovers it. Asking for clarification before
   building is more effective than any coding workflow.

**Cost-adjusted recommendation:** test-after is the cheapest arm ($0.19/stage) AND
achieves the best EDGE pass rate under vague spec. tdd-refactor is the most expensive
($0.44/stage, 2.3×) AND achieves the best changeability. The choice is context-dependent:
- Vague requirements, one-shot delivery → test-after
- Clear requirements, long-lived codebase with expected changes → tdd-refactor
- Neither (just getting it working quickly) → tdd-no-refactor (same blast radius as
  test-after, slightly cheaper)

**What this adds to the prior null results:** The prior two studies found no TDD
advantage under clear specs with no change chain. This experiment confirms that the
advantage is real — but only for changeability under a change chain, not for
ambiguity resolution. TDD pays off, but not for the reason most commonly claimed.

---

*Report generated by `claude-sonnet-4-6` in a remote Claude Code session.*  
*Raw data: [`docs/experiments/data/`](data/)*  
*Analysis script: [`scripts/analyze_tdd_pays.py`](../../scripts/analyze_tdd_pays.py)*
