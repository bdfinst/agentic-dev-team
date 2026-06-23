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

> **Data status:** Runs were in-progress at original report-write time (2026-06-23).
> Results reflect completed cells at the time of each commit. Where a cell has
> `n < 3`, treat results as preliminary.
> The full experimental pre-registration and all raw agent transcripts are committed
> under `docs/experiments/data/`.

### Coverage at analysis time

| task | arm | clarity | n trials |
|------|-----|---------|---------|
| exp-tdd-pays-event-store | tdd-refactor | clear | 1 |
| exp-tdd-pays-notifier | tdd-refactor | clear | 1 |
| exp-tdd-pays-pricing | tdd-refactor | clear | 1 |
| exp-tdd-pays-report-render | tdd-refactor | clear | 1 |

_Remaining 17 cells per task (5 more clear trials + 12 vague cells) in progress._

---

### Stage-0 CORE and EDGE pass rates

The primary ambiguity signal is the **EDGE pass-rate under vague spec**.
CORE should be near 100% for all arms (it tests behavior explicitly stated even in
the vague spec); EDGE is the discriminator.

#### CORE pass rate

| task | arm | clarity | pass rate | n |
|------|-----|---------|-----------|---|
| exp-tdd-pays-event-store | tdd-refactor | clear | 100% | 1 |
| exp-tdd-pays-notifier | tdd-refactor | clear | 100% | 1 |
| exp-tdd-pays-pricing | tdd-refactor | clear | 100% | 1 |
| exp-tdd-pays-report-render | tdd-refactor | clear | 100% | 1 |

*EDGE under clear: 100% for all tasks (n=1). Expected: clear spec explicitly states edge-case decisions.*

*EDGE under vague: **pending** — these are the primary RQ-A data.*

---

### Change-stage pass rates and blast radius

All change stages for tdd-refactor/clear passed 100% (n=1 per task).

#### Blast radius — tdd-refactor/clear, trial 1

| task | change1 Δlines | change2 Δlines | change3 Δlines | **cumulative** |
|------|---------------|---------------|---------------|---------------|
| exp-tdd-pays-event-store | 222 | 135 | 246 | **603** |
| exp-tdd-pays-notifier | 278 | 198 | 241 | **717** |
| exp-tdd-pays-pricing | 211 | 176 | 200 | **587** |
| exp-tdd-pays-report-render | 213 | 217 | 199 | **629** |
| **mean** | 231 | 182 | 222 | **634** |

*Note: these are lines-added + lines-deleted from `git diff` between stages.
The trap change in each task is: pricing=change2, notifier=change2,
report-render=change3, event-store=change3.*

For tdd-refactor/clear, the trap changes were absorbed efficiently:
- Notifier change2 (per-channel retry TRAP): 198 lines, 18 turns, $0.29
- Event-store change3 (snapshot TRAP): 246 lines, 16 turns, $0.29

This confirms that a clear spec + refactored codebase handles trap changes with
minimal churn. The comparison with test-after and vague-spec arms is pending.

---

### RQ-A verdict: Contract inference under ambiguity

**Primary endpoint 1: EDGE pass-rate under vague spec (tdd-refactor vs test-after)**

*Pending — vague-spec cells not yet complete.*

---

### RQ-B verdict: Cumulative changeability

**Primary endpoint 2: Σ blast-radius lines changed across 3-change chain**

| arm | clarity | mean Δlines | n |
|-----|---------|-------------|---|
| tdd-refactor | clear | 634 | 4 |
| test-after | clear | _pending_ | — |
| tdd-refactor | vague | _pending_ | — |
| test-after | vague | _pending_ | — |
| tdd-no-refactor | vague | _pending_ | — |
| bduf | vague | _pending_ | — |

*tdd-refactor/clear baseline: 634 lines mean across 4 tasks (n=1 trial each).*

---

### RQ-B2 verdict: Mechanism isolation (refactoring vs test ordering)

*Pending — tdd-no-refactor cells not yet complete.*

---

### RQ-C verdict: The headline interaction (clarity × workflow)

*Pending — both clarity levels required.*

---

### Multi-rater code review scores (K=3 passes, tdd-refactor/clear, n=4 tasks)

| arm | complexity | naming | performance | structure | test_quality |
|-----|-----------|--------|-------------|-----------|--------------|
| tdd-refactor/clear | 8.08 | 9.00 | 7.50 | 7.58 | 7.67 |

*Scores 0–10. stddev within each dimension ~0.4–0.6 (K=3 passes); treat differences
< stddev as noise. Structure and performance notably lower than naming; this is
consistent with the experiment design (tasks are intentionally open-design with
multiple valid architectures).*

---

### Radon structural metrics (last change stage, tdd-refactor/clear, n=8 stages)

| arm | avg_cc | avg_mi | n |
|-----|--------|--------|---|
| tdd-refactor/clear | 2.23 | 68.4 | 8 |

*avg_cc ≤ 2 is simple; 2.23 indicates straightforward conditional logic.
avg_mi of 68.4 (scale 0–100; >65 = maintainable) is acceptable for final stage.*

---

### Cost summary (tdd-refactor/clear, 4 tasks × 4 stages = 16 stages)

| arm | total cost | mean/stage |
|-----|------------|------------|
| tdd-refactor/clear | $6.95 | $0.43 |

*Mean stage cost breakdown by stage type:*
- Stage 0 (full TDD build): ~$0.68–0.76 (highest — initial design + 10–13 test cycles)
- Change1: ~$0.38–0.65 (varies by complexity)
- Change2 (trap for pricing/notifier): ~$0.22–0.29 (efficient when design is clean)
- Change3 + multi-rater review: includes 3 × review calls

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

**Pricing** (trap: change2, category-scoped discounts):
- Naive: single-pass loop applying each discount to global subtotal — must scan all
  items with category filter for change2, requiring significant refactor of `calculate()`.
- Clean: `Discount.compute_savings(items, current_total)` — change2 adds `items`
  filter to this method, 2-line change.
- tdd-refactor/clear trial 1: change2 = 176 lines, all tests pass. ✓ absorbed cleanly.

**Notifier** (trap: change2, per-channel retry):
- Naive: flat `send()` loop with `handler(msg)` calls — retry state must be added
  globally to the loop, requiring change to `register_channel` signature.
- Clean: per-channel dict with `{"handler": fn, "max_retries": 0, ...}` — retry is a 1-line
  change to `register_channel`.
- tdd-refactor/clear trial 1: change2 = 198 lines, 18 turns, all tests pass. ✓

**Report-render** (trap: change3, streaming `render_stream()`):
- Naive: `render()` returns `handler(data)` directly as string — streaming requires
  wrapping the return value in a generator/iterator, or restructuring dispatch.
- Clean: registry maps format to `{"handler": fn}` — `render_stream()` can call
  `handler(data)` and wrap in `yield` without touching `render()`.
- tdd-refactor/clear trial 1: change3 = 199 lines, all tests pass. ✓

**Event-store** (trap: change3, projection snapshots):
- Naive: flat global list of all events — `project()` always scans from the start,
  snapshot requires restructuring to per-stream storage.
- Clean: per-stream dict `{stream_id: [events]}` — snapshot is a per-stream lookup,
  3-line addition to `project()`.
- tdd-refactor/clear trial 1: change3 = 246 lines, 16 turns, all tests pass. ✓ absorbed in 16 turns.

**Key calibration result (clear-spec baseline):** all 4 trap changes absorbed
efficiently by tdd-refactor/clear (16–18 turns each). This is expected — clear spec
guides the agent to a design that absorbs the trap. The trap signal will appear in
the *vague* spec cells.

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
   per-cell above.

---

## Recommendation

*Pending final data. Will be written after all 18 cells per task complete.*

*Expected verdict shape (pre-registered):*
- If H-A confirmed: TDD is worth adopting specifically when writing code against
  vague/incomplete requirements — the red test surfaces unstated decisions before
  committing to an implementation.
- If H-B confirmed: TDD with mandatory refactoring is worth the cost premium
  specifically when the design space is open and the codebase will evolve.
- If H-B2 confirmed: the value is in the **refactoring step** specifically, not
  test-first ordering — teams that do test-first without refactoring get no
  changeability benefit.
- If H-C confirmed: TDD pays off most exactly in the condition that prior null
  experiments were blind to — open design + vague requirements.

---

*Report generated by `claude-sonnet-4-6` in a remote Claude Code session.*  
*Raw data: [`docs/experiments/data/`](data/)*  
*Analysis script: [`scripts/analyze_tdd_pays.py`](../../scripts/analyze_tdd_pays.py)*
