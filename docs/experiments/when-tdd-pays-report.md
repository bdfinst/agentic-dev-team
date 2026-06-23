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
- **H-B2 (mechanism):** `tdd-no-refactor` ≈ `test-after` < `tdd-refactor`;
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

> **Data status:** Runs were in progress at report-write time. Results below reflect
> completed cells and are updated as cells complete. Where `n < 3`, results are
> preliminary. The full experimental pre-registration and all raw agent transcripts
> are committed alongside this report under `docs/experiments/data/`.

### Coverage at analysis time

<!-- DATA: data_coverage -->

_See [raw data files](data/) for per-stage JSONL._

---

### Stage-0 CORE and EDGE pass rates

The primary ambiguity signal is the **EDGE pass-rate under vague spec**.
CORE should be near 100% for all arms (it tests behavior explicitly stated even in
the vague spec); EDGE is the discriminator.

<!-- DATA: stage0_grid_core -->

<!-- DATA: stage0_grid_edge -->

---

### RQ-A verdict: Contract inference under ambiguity

**Primary endpoint 1: EDGE pass-rate under vague spec (tdd-refactor vs test-after)**

<!-- DATA: rq_a -->

---

### Change-stage pass rates and blast radius

<!-- DATA: change_grid -->

---

### RQ-B verdict: Cumulative changeability

**Primary endpoint 2: Σ blast-radius lines changed across 3-change chain**

<!-- DATA: rq_b -->

---

### RQ-B2 verdict: Mechanism isolation (refactoring vs test ordering)

<!-- DATA: rq_b2 -->

---

### RQ-C verdict: The headline interaction (clarity × workflow)

<!-- DATA: rq_c -->

---

### Multi-rater code review scores

K=3 passes of a blind structural review at the final change stage, mean ± stdev.
Differences smaller than the stdev are treated as noise.

<!-- DATA: review -->

---

### Radon structural metrics

<!-- DATA: radon -->

---

## Discussion

### Prior context

The two prior experiments ([`tdd-vs-nontdd-report.md`](tdd-vs-nontdd-report.md),
[`3sizes-3arms-report.md`](3sizes-3arms-report.md)) found **no significant advantage
for test-first** across a range of task sizes. Both studies used clear specs and
single-shot tasks with no change chain — precisely the conditions where TDD's claimed
benefits (ambiguity resolution and design improvement under feedback) are absent.

This experiment adds both missing conditions simultaneously: vague specs that leave
real decisions unstated, and a multi-stage change chain that punishes rigid
designs.

### Design trap calibration

Each task's trap was calibrated by running both a naive and a clean reference
implementation (in the scratchpad, not committed):

- **Pricing:** Naive passes 8/8 CORE + at least 5/6 EDGE at Stage 0, but change2
  (category-scoped discounts) requires restructuring `calculate()` to pass items
  per discount rather than a global subtotal. Clean passes change2 with 3-line
  addition to `Discount.compute_savings()`.
- **Notifier:** Naive passes Stage 0, but change2 (per-channel max_retries) requires
  adding per-channel state that a flat loop doesn't carry. Clean uses a channel
  wrapper/registry.
- **Report-render:** Naive passes Stage 0 and most EDGE, but change3
  (render_stream()) requires a streaming dispatch path. Clean dispatches through a
  format registry that can route to either mode.
- **Event-store:** Naive passes Stage 0, but change3 (projection snapshots) requires
  snapshot state per stream. Clean stores events per-stream and adds a snapshot
  dict with negligible diff.

### Vagueness calibration note

The vague specs were authored to omit architecture guidance and edge-case decisions
without making the task impossible. Expected profile: CORE ~100%, EDGE 50–80% (some
missed, some inferred correctly). If a task shows EDGE ~100% under vague, the vague
spec leaked too much; if EDGE ~0%, the task was under-specified.

Report-render is the weakest EDGE discriminator: 5 of 6 edge assertions test
behaviors (None pass-through, exception propagation, column ordering) that a
reasonable implementation handles naturally even without being told. The trap signal
comes from change3, not Stage-0 EDGE.

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
   As seen in the prior naming-agent run (0/19/4 on near-identical code), LLM
   reviewer variance can be high. The deterministic blast-radius and EDGE counts are
   primary; review scores are secondary and reported with stdev.
5. **Report-render weak EDGE calibration** (noted above). The primary signal for
   that task is the change3 trap, not Stage-0 EDGE.
6. **Runs in cloud ephemeral container.** If the session expired before all cells
   completed, some cells may have fewer than 3 trials. Coverage is reported
   per-cell in the Data Coverage table.

---

## Recommendation

<!-- To be written after results are complete. -->
_Pending final data. See RQ-A/B/C verdicts above._

---

*Report generated by `claude-sonnet-4-6` in a remote Claude Code session.*  
*Raw data: [`docs/experiments/data/`](data/)*  
*Analysis script: [`scripts/analyze_tdd_pays.py`](../../scripts/analyze_tdd_pays.py)*
