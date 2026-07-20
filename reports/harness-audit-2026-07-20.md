# Harness Audit Report

**Date**: 2026-07-20
**Metrics period**: single input — `reports/orchestration-benchmark-2026-07-18.md` (45/45 runs, 2026-07-18)
**Review runs analyzed**: 45 benchmark runs (3 arms × 3 classes × 5 reps); 0 runtime review-value/session-digest records available in this checkout

> **Scope of this audit.** This is the #1195 follow-up mandated by the #1095
> decision rule ("if A dominates B on a class, that is a finding to report —
> it feeds `/harness-audit`") and ADR 0022. Its input is the #1099
> orchestration benchmark, not accumulated runtime metrics — the
> `review-value.jsonl`, `session-digest.jsonl`, and `eval-ablation.jsonl`
> streams the periodic audit normally consumes are absent here, so those
> sections are reported as no-data rather than fabricated. The audit is
> **report-only** (orchestrator constraint 1): every recommendation below
> feeds a human gate, and none of them are applied by this PR.

## Re-baseline Required (eval baseline)

Not present. `evals/baseline.json` carries no `model` field (pre-migration
baseline), so Step 2 adds no eval-rebaseline section — this is silent
success, not a finding. **This is distinct from the benchmark re-baseline
discussed under Orchestration below**, which is warranted for a different
reason (#1178 landing).

## Review Agent Effectiveness

> Source: `metrics/*-task-log.jsonl`, `/apply-fixes` correction data.
> **Insufficient data** — no per-agent finding/dismissal records are logged
> in this checkout. The benchmark measured end-to-end arm cost/quality, not
> per-review-agent finding rates, so no removal / false-positive / low-value
> candidate can be derived from it. Re-run this section once
> `review-value.jsonl` has ≥10 logged reviews.

### Removal Candidates (zero fail findings)
| Agent | Reviews | Pass rate | Recommendation |
|-------|---------|-----------|----------------|
| — | — | — | No data |

## Review-Value Fix Rates (inline checkpoint ROI)

> Source: `metrics/review-value.jsonl` — **absent**. No `/build` runs logged
> in this checkout, so per-checkpoint fix rates cannot be computed and no
> drop-candidate / high-value-checkpoint verdict is issued.

## Lesson Validation (validated-outcome weighting, #866)

> Source: `metrics/config-changelog.jsonl` (present) ×
> `metrics/session-digest.jsonl` (**absent**). Because the digest side is
> absent, every adopted lesson would resolve to **insufficient data** — a
> data condition, never reported as `neutral`. `lesson_validate.py` was
> **not** run with `--apply`: with no digest there are no verdicts to append,
> and an append here would conflict with concurrent PRs against the shared
> changelog. No rollback proposals.

- Lessons validated / neutral / harmful / insufficient data: 0 / 0 / 0 / all (no digest)
- Rollback proposals: 0

## Model Routing Recommendations

The benchmark's most consequential routing finding is not a per-agent tier
mismatch — it is that **shipped effort-band routing never fired at all**.
Environment deviation 1 + 3 (report) / finding 2 (ADR 0022): on CLI 2.1.214
a plugin's `settings.json` hooks do not load, and the `model` subagent
parameter silently ignores full snapshot IDs, so `knowledge/model-routing.json`
could never take effect. Both arms had to be locally repaired before the band
mechanism was observable (139k haiku tokens in arm C complex once repaired).

**#1178 ("effort-band model routing never fires on current Claude Code") is
now CLOSED.** That closes the routing-layer defect the benchmark had to work
around — and it is exactly ADR 0022 revisit-trigger 1. Consequence for this
audit: shipped band economics have *still* never been measured natively; the
benchmark's absolute costs are a locally-repaired approximation. No per-agent
tier change is recommended off this evidence.

| Agent | Current tier | Suggested tier | Rationale |
|-------|-------------|----------------|-----------|
| — | — | — | No per-agent tier change recommended; routing layer only just became live (#1178). Re-measure before re-tiering. |

## Orchestration Simplification Opportunities

This is the substantive section. The benchmark's headline is a property of
the **default dispatch posture itself**, not of the rejected #1092/#1093
treatment: the solo arm dominated the released pipeline on every tested class.

| Class | A — solo | B — released | A advantage |
| --- | --- | --- | --- |
| trivial (1-file fix) | $0.17, 5/5, 24 s | $0.65, 5/5, 75 s | 3.8× cheaper, equal quality, 3.1× faster |
| standard (4-file feature) | $0.27, 5/5, 46 s | $0.75, 5/5, 123 s | 2.8× cheaper, equal quality, 2.7× faster |
| complex (26-file review) | $0.75, 5/5, 155 s | $2.26, **4/5**, 329 s | 3.0× cheaper, **better** quality, 2.1× faster |

Three independent signals fall out of this, ranked by how safe they are to
act on **now**:

### 1. Output-contract handoff loss — act now, not cost-gated (highest priority)

Both orchestrated quality failures (`r2-complex-B`, `r3-complex-C`) completed
their reviews but never wrote the required `REVIEW_FINDINGS.json` — recall
scored 0.0. The contract was lost crossing the delegation boundary. Arm A
honored the contract in all 15 of its runs.

- **Rate**: 2 of 30 orchestrated runs (both arms) = **6.7% silent
  contract-loss**, concentrated entirely in the complex (fan-out) class:
  2 of 10 complex-orchestrated runs = **20%**.
- This is a **correctness defect, not an economics one.** It does not depend
  on the fixture family, the session model, or the #1178 routing repair, and
  it is the reason the pipeline *lost on quality* on the one class
  orchestration is supposed to win. It is safe and correct to fix regardless
  of any re-baseline.
- **Recommendation**: harden the delegation output contract so a review that
  completes but emits no `REVIEW_FINDINGS.json` is a hard, surfaced failure
  (verify-and-retry the artifact write across the boundary; treat a missing
  findings file as red, never as a silent pass). File as its own issue — this
  is the one finding that should not wait on a re-baseline.

### 2. Solo-by-default below a size threshold — directionally strong, magnitude pending re-baseline

A dominates B at every class with no crossover in the tested range, and the
gap is largest where the delegation ceremony has least to amortize (trivial:
3.8×). This is the strongest support for raising the dispatch threshold so
small tasks stay solo by default.

- **Caveat (do not hardcode a threshold from these numbers).** Two of the
  three ADR 0022 revisit triggers bear directly on the magnitude: (1) #1178
  has now landed, so native routing changes the cost structure the benchmark
  approximated; and the fixture-overfitting caveat is permanent — three
  fixture shapes, numbers must not be quoted beyond that family. The
  *direction* (A cheaper, equal-or-better quality) is robust across the
  family; the *break-even file count* is not yet measured on live routing.
- **Recommendation**: re-run the #1095 protocol via
  `/orchestration-benchmark` now that #1178 is closed (trigger 1 satisfied),
  then set the solo-by-default threshold from the re-baselined crossover — do
  not write a threshold into `/plan`'s complexity classification off the
  locally-repaired numbers. Provisional interim posture: prefer solo for
  trivial/standard (≤ ~4-file) shapes, since the direction there is not
  plausibly reversible within the fixture family.

### 3. Review fan-out tail cost — trim the wide-sweep dispatch, pending re-baseline

The complex-B cost tail reached **$8.04** on a single 26-file review (median
$2.26). The expensive component on wide sweeps is the review fan-out, not the
implementation.

- **Recommendation**: on wide, single-file-granularity review sweeps, cap or
  batch the review fan-out rather than dispatching the full agent set
  per-file. Also re-baseline-gated (the absolute tail moves with #1178), but
  the tail's existence is a real signal that fan-out on wide sweeps is the
  dominant cost lever. Feeds the same re-run as #2.

### Benchmark re-baseline status

ADR 0022 revisit-trigger 1 has fired (#1178 closed) but **no re-baseline has
been run** — no benchmark report dated after 2026-07-18 exists. Until it is,
the posture changes in #2 and #3 remain recommendations, not committed
config. Trigger 2 (task shapes outside the matrix — e.g. deeply-coupled
100-file migrations) and trigger 3 (order-of-magnitude band-pricing shift)
remain unfired.

## Summary

- Agents to consider removing: 0 (no per-agent runtime data)
- Model tier changes suggested: 0 (routing layer only just became live via #1178 — re-measure first)
- Orchestration simplifications: 3 (contract-handoff hardening; solo-by-default threshold; review fan-out trim)
- Review-value drop candidates: 0 (no data)
- Review-value high-value checkpoints: 0 (no data)
- Re-baseline required (eval baseline): no (pre-migration `model` field)
- Benchmark re-baseline warranted: **yes** — #1178 (ADR 0022 trigger 1) landed; re-run #1095 protocol before committing posture changes 2 & 3
- Lessons validated / neutral / harmful / insufficient data: 0 / 0 / 0 / all (no session-digest)
- Rollback proposals (harmful verdicts): 0

## Next Steps

Prioritized by how safe each is to act on today:

1. **Harden the output-contract handoff (act now).** A completed review that
   emits no `REVIEW_FINDINGS.json` must fail loudly across the delegation
   boundary, never pass silently. Not cost- or fixture-gated; it is the cause
   of the only quality regression measured. File as a standalone `fix:` issue.
2. **Re-run the #1099 benchmark on live routing.** #1178 is closed
   (ADR 0022 trigger 1); re-baseline via `/orchestration-benchmark` on the
   #1095 protocol so the solo-by-default threshold and fan-out-trim
   magnitudes rest on native band routing, not the locally-repaired
   approximation. File as a `chore:` re-baseline issue.
3. **After the re-baseline, gate the posture changes.** Set the
   solo-by-default dispatch threshold (item 2) and the wide-sweep review
   fan-out cap (item 3) from the re-baselined crossover, at a human gate. Do
   **not** hardcode either from the 2026-07-18 numbers — the fixture-overfitting
   caveat is permanent and the routing layer changed underneath them.
4. **Restore the runtime metric streams for the next periodic audit.**
   `review-value.jsonl`, `session-digest.jsonl`, and `eval-ablation.jsonl`
   were absent this run, so the standard per-agent effectiveness / fix-rate /
   lesson-validation sections could not be computed. Accumulate ≥10 logged
   reviews before the next `/harness-audit`.
