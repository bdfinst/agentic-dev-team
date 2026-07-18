# 22. Reject the delegation-only sweep — delegation must earn its measured overhead

Date: 2026-07-18

## Status

Accepted

## Context

The 2026-07-16 competitive analysis of Anthropic's CMA "plan big, execute
small" cookbook proposed two dispatch changes: a fan-out-economics knowledge
file (#1092) and a delegation-only sweep rule (#1093) under which the
orchestrator never reads beyond classification-sized probes and pushes all
bulk reading to low-band workers. The cookbook's own benchmark claimed
~2.5× cost reduction at matched rigor. Per this repo's measurement rule
("measure friction — don't assume it; every claim names its instrument"),
the epic #1097 required the treatment to be built on an experiment branch
and beaten against the released plugin **before** shipping — the
pre-registered protocol lives in #1095, the run in #1099.

The experiment ran on 2026-07-18: 3 arms (solo session / released plugin
10.12.0 / treatment branch) × 3 task classes (one-file fix, 4-file feature
slice, 26-file review sweep) × 5 interleaved reps, 45/45 runs completed at
matched external acceptance checks. Evidence:
[`reports/orchestration-benchmark-2026-07-18.md`](../../reports/orchestration-benchmark-2026-07-18.md)
(raw per-run data alongside).

Measured, per class (median cost per run; quality = acceptance passes):

| Class | Solo | Released | Treatment | Treatment vs released |
| --- | --- | --- | --- | --- |
| trivial | $0.17 (5/5) | $0.65 (5/5) | $0.55 (5/5) | −14.4% (below bar; spreads overlap) |
| standard | $0.27 (5/5) | $0.75 (5/5) | $0.86 (5/5) | **+14.6%** |
| complex | $0.75 (5/5) | $2.26 (4/5) | $5.81 (4/5) | **+157%** |

The sweep mechanism itself worked where it engaged: on the complex class the
treatment moved median low-band reading tokens from 666 to 139,091 —
and still cost 2.6× more, because dispatch ceremony plus high-band review
fan-out added more spend than cheap reading saved. On the standard class the
rule never engaged despite crossing its own >3-file threshold. The predicted
task-size crossover (above which delegation wins) does not exist in the
measured range: the treatment's loss **grows** with task size.

Two findings beyond the treatment itself:

1. **The solo arm dominated the released pipeline on every class** — 3–4×
   cheaper, equal or better quality (15/15 acceptance passes vs 14/15; both
   orchestrated failures lost the output contract across the delegation
   boundary), roughly 2× faster.
2. The experiment's pilot discovered that the shipped hook layer (including
   effort-band routing) **does not load at all** on current Claude Code
   (#1178) — routing had to be repaired identically in both arms before the
   mechanism was even observable. Shipped band-routing economics had never
   actually been exercised.

## Decision

**Reject #1092/#1093** per the pre-registered decision rule (no arm-C win at
any task class): the fan-out-economics knowledge file and the
delegation-only sweep rule do not ship. The experiment branch is deleted;
the closed issues carry the report as evidence. Recorded at the #1100 Phase
4 gate by the maintainer.

The general principle this ADR fixes: **delegation must earn its overhead
with a measured win at matched rigor before it ships as default dispatch
behavior.** A mechanism that demonstrably moves tokens to a cheaper band is
still rejected if the end-to-end cost rises — the mechanism check is
necessary, not sufficient.

**Revisit triggers** — reopen (as a new experiment on the same #1095
protocol, not by reverting this ADR) when any of:

1. the #1178 hook-layer fixes land and shipped band routing is verified live
   — this experiment measured a locally-repaired approximation of routing,
   and a natively-working hook layer changes the cost structure enough to
   justify a re-run;
2. a task shape materially outside the tested matrix becomes a routine
   workload (e.g. deeply-coupled 100-file migrations where batching
   economics differ from independent-file review sweeps);
3. per-model pricing shifts change the band spread by an order of magnitude.

## Consequences

**Easier:**

- Cost-increasing dispatch ceremony is kept out of the shipped orchestrator;
  the negative result prevented a +15–157% cost regression riding in on a
  cookbook benchmark's authority.
- The A-dominates-B finding is now on the record as `/harness-audit` input:
  the released pipeline's default dispatch posture — not just the rejected
  treatment — has a measured cost/quality case to answer on these task
  shapes.
- Future "add more delegation" proposals have a pre-registered protocol
  (#1095, `/orchestration-benchmark`) and a precedent for how they must be
  evaluated before shipping.

**Harder / risks:**

- The fixture-overfitting caveat is permanent: three fixture shapes were
  tested, and the numbers must not be quoted beyond that family. The
  revisit triggers exist precisely because the boundary of the evidence is
  narrow.
- The finding is entangled with one environment reality: routing had to be
  locally repaired (#1178) in both arms. The comparison between arms is
  clean, but absolute costs may shift once the shipped hook layer works
  natively — trigger 1 covers this.
