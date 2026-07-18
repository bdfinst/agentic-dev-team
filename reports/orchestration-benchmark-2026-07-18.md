# Orchestration Benchmark — delegation-economics A/B (#1099) (2026-07-18)

**Date**: 2026-07-18
**Target**: dev-team plugin — solo session vs released orchestration (10.12.0, `03b74ad`) vs delegation-only-sweep branch (`experiment/delegation-economics`, `f15884f`)
**Tool versions**: Claude Code CLI 2.1.214; cost meter from `main` (post-#1094, `by_agent_type`-capable); session model `sonnet` (billed `claude-sonnet-5`) all arms
**Scope**: pre-registered #1095 protocol — 3 arms × 3 task classes × 5 reps, interleaved A,B,C, isolated headless runs; 45/45 runs completed, 0 discarded

## Executive summary

**No arm-C adoption case exists at any task class.** The delegation-only sweep
rule (#1092/#1093 treatment) never produced a cost reduction that survives the
pre-registered decision rule: −14.4% on trivial (below the 25% bar, spread-
overlapped), **+15% cost on standard**, and **+157% cost on complex** — the
sweep mechanism did engage on the complex class (median low-band tokens rose
from 666 to 139,091), but delegation ceremony and high-band review dispatch
added more spend than low-band reading saved.

**The headline finding is about arm A, not arm C: the solo session dominated
both orchestrated arms on every class** — cheapest (3–4× cheaper than B), of
equal or better quality (15/15 acceptance passes vs 14/15 for B and C), and
fastest. Per the pre-registered rule this finding is reported, not
suppressed, and feeds `/harness-audit`.

Pre-registered decision-rule outcome: **Reject arm C** (recommendation to the
#1097 Phase 4 human gate). The A-dominates-B result additionally puts the
default dispatch pipeline itself in question for task shapes like these.

## Per-class results

Cost is per-run dollars (CLI-reported `total_cost_usd`); spread is min–max
over 5 runs; band share is the median run's token distribution across
haiku/sonnet/opus.

### Trivial (one-file bug fix, 8 tests)

| Arm | Cost median [min–max] | Wall median | Quality | Band share h/s/o |
| --- | --- | --- | --- | --- |
| A — solo | **$0.172** [0.170–0.172] | 24 s | 5/5 | 0.2% / 99.8% / 0 |
| B — release | $0.646 [0.546–0.845] | 75 s | 5/5 | 0.1% / 99.9% / 0 |
| C — branch | $0.553 [0.511–0.676] | 77 s | 5/5 | 0.1% / 99.9% / 0 |

C vs B: −14.4% (below the 25% bar; spreads overlap → null). No low-band
shift (C median haiku tokens 611 = B's 611) → mechanism check **fails**.

### Standard (4-file feature slice, 13 tests)

| Arm | Cost median [min–max] | Wall median | Quality | Band share h/s/o |
| --- | --- | --- | --- | --- |
| A — solo | **$0.265** [0.259–0.309] | 46 s | 5/5 | 0.2% / 99.8% / 0 |
| B — release | $0.749 [0.697–0.826] | 123 s | 5/5 | 0.1% / 99.9% / 0 |
| C — branch | $0.858 [0.708–1.294] | 144 s | 5/5 | 0.1% / 99.9% / 0 |

C vs B: **+14.6% more expensive** (and the widest spread of any cell). No
low-band shift (598 vs 598 haiku tokens) → the sweep rule did not engage on a
4-file task despite its >3-file threshold; the added cost is pure treatment
ceremony. Mechanism check **fails**.

### Complex (26-file review sweep; ground truth 17 defective / 9 clean)

| Arm | Cost median [min–max] | Wall median | Quality | Band share h/s/o |
| --- | --- | --- | --- | --- |
| A — solo | **$0.752** [0.660–0.948] | 155 s | 5/5 | 0.2% / 99.8% / 0 |
| B — release | $2.259 [2.034–8.038] | 329 s | 4/5 | 0 / 96.9% / 3.1% |
| C — branch | $5.811 [1.848–7.920] | 573 s | 4/5 | 4.3% / 78.6% / 17.1% |

C vs B: **+157% more expensive at the median.** The mechanism *did* engage —
median haiku tokens 139,091 (C) vs 666 (B), the intended low-band reading
shift — but total cost rose because the sweep added dispatch ceremony plus a
17% opus share (high-band reviewers) on top of, not instead of, the baseline
work. Mechanism check: **direction passes, economics invert** — under the
pre-registered rule this is not a win in any case because cost increased.

Quality failures (both orchestrated arms): `r2-complex-B` and `r3-complex-C`
completed their reviews but never wrote the required `REVIEW_FINDINGS.json`
(recall scored 0.0) — the output contract was lost across the delegation
boundary. Arm A honored the contract in all 15 of its runs across classes.

## Crossover threshold

**None found.** The #1095 protocol predicted a task-size crossover above
which arm C wins; within this matrix C loses at every size, and the loss
*grows* with task size (−14.4% → +14.6% → +157%). There is no threshold to
write into the #1093 sweep rule. (Fixture-overfitting caveat: this
generalizes only as far as the three fixture shapes tested — see Threats.)

## Decision-rule outcomes (pre-registered in #1095)

| Class | Adopt C over B? | Reason |
| --- | --- | --- |
| trivial | **No** | −14.4% < 25% bar; spreads overlap; mechanism check fails |
| standard | **No** | Cost increased; mechanism check fails |
| complex | **No** | Cost +157%; mechanism direction passed but produced added cost, not savings |

| Class | Retain B over A? | Reason |
| --- | --- | --- |
| trivial | **No** — A dominates | A 3.8× cheaper, equal quality |
| standard | **No** — A dominates | A 2.8× cheaper, equal quality |
| complex | **No** — A dominates | A 3.0× cheaper, *better* quality (5/5 vs 4/5), 2.1× faster |

Per the rule: the A-dominates-B finding is reported and feeds
`/harness-audit`. Recommendation to the Phase 4 gate: **Reject** —
close #1092/#1093 as not-planned with this report as evidence, delete the
experiment branch. The negative result is the deliverable.

## Threats to validity

1. **Unmatched rigor** — controlled: acceptance checks are external to all
   arms (harness-run pytest with test-hash verification; findings-recall
   grader against a fixed manifest) and identical per class. The two
   orchestrated failures were contract failures, not weaker checks.
2. **Fixed-overhead asymmetry** — sampled: the trivial class exists to
   expose it, and does (B/C pay 3–4× on a one-file fix).
3. **Cache warmth** — controlled: arm order interleaved A,B,C within every
   rep×class cell; the schedule executed as planned (run log).
4. **Model drift** — controlled: band→model map identical in both arms and
   unchanged across the experiment; exact billed model IDs recorded per run.
   Note the map was switched to dispatch-layer aliases (deviation 3 below)
   before the first counted run.
5. **Fixture overfitting** — acknowledged: three fixture shapes (single-file
   pytest fix, few-file pytest feature, wide single-file-granularity review
   sweep). The complex fixture's files are independent single-file review
   targets, which favors batching less than a deeply-coupled 20-file diff
   might; the A-dominance margin (3×, with a quality edge) is large enough
   that the direction is unlikely to flip within this family of shapes, but
   the numbers should not be quoted beyond it.

## Run log

- **Pinned band→model map** (both arms, identical): low→haiku,
  medium→sonnet, high→opus (dispatch-layer aliases; deviation 3). Billed
  IDs observed: `claude-haiku-4-5-20251001`, `claude-sonnet-5`,
  `claude-opus-4-8`.
- **Schedule**: reps 1–5; within each rep, classes trivial→standard→complex;
  within each cell, arms A→B→C. Executed exactly as planned; timestamps in
  `orchestration-benchmark-2026-07-18-data/runs.jsonl`.
- **Discarded runs**: none. 45/45 completed; the two acceptance failures are
  counted as failures, not discarded.
- **Excluded**: a 9-run pre-patch pilot (broken routing — see Deviations)
  is preserved separately as the discovery record and excluded from analysis.
- **Raw data**: `orchestration-benchmark-2026-07-18-data/` — per-run records
  with CLI usage, cost-meter `by_model`/`by_thread`/`by_agent_type`,
  acceptance detail (`runs.jsonl`); aggregates (`summary.json`); pinned
  environment + deviations (`environment.json`); install manifest with both
  build SHAs (`install-manifest.json`).

## Environment deviations (identical in both arms; recorded before first counted run)

Discovered by the pilot and applied to **both** installs equally (issue
#1178 tracks the upstream fixes):

1. Plugin hook registrations moved to user-level config: on CLI 2.1.214 a
   plugin's `settings.json` hooks never load (`hooks/hooks.json` is the
   supported mechanism), so the shipped hook layer — including band routing —
   was dead in both builds.
2. `agent_model_resolve.py` tool-name gate widened to accept `Task` (inert:
   live hook payloads carry `Agent`).
3. `knowledge/model-routing.json` values switched from full model snapshot
   IDs to dispatch-layer aliases — the subagent `model` parameter silently
   ignores full IDs, so the shipped map could never take effect.

Without these, no arm can move tokens across bands and the experiment cannot
test its question; with them, the mechanism check became observable (139k
haiku tokens in arm C complex runs).

## Provenance

- Repository: `/home/user/agentic-dev-team` (bdfinst/agentic-dev-team)
- Branch / SHA: control `main` / `03b74ad` (release dev-team-v10.12.0); treatment `experiment/delegation-economics` / `f15884f`
- Run parameters: 3 arms × 3 classes × 5 reps, interleaved; session model `sonnet`; timeouts 900/1800/2400 s per class; isolated per-run HOME + config copies
- `dev-team` plugin version: control 10.12.0; treatment 10.11.0 (branch, unbumped by design — SHA is the identity)
