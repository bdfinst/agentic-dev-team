# Spike — /build token cost: per-agent overhead & review-value no-op rates

Answers the questions in #1512 (part of epic #1511). **Deliverable is analysis, not code.**

## TL;DR

- **CORRECTION (verified at #1513 build-time):** this spike's original claim that "the
  instrumentation does not exist" was **wrong**. Per-subagent attribution already ships (#1094):
  `cost_meter.py report --json` produces a full `by_agent_type` breakdown and reads the sibling
  `subagents/agent-*.jsonl` files — confirmed on a live transcript with subagent turns (15 agent-type
  buckets: `main` + every dispatched lens). The original "only `main`" reading was a sampling
  artifact — the sampled `cost-metering.jsonl` records were written before any subagent was
  dispatched. So per-agent overhead (Q1), spawn break-even (Q2), and the fan-out multiplier (Q3) **are
  measurable today** via `cost_meter report --json <transcript>`. The only real gap #1513 closed was
  persisting `cache_creation_input_tokens` (the F component) in the durable `cost-metering.jsonl`, not
  just in the on-demand report.
- **The review-value sample is far too thin and biased to prune any lens (Q4).** 10 records total,
  ~100% "found something" on nearly every lens — because the only slices that got logged happened
  to have findings. This is a sampling artifact, not evidence a lens is valuable. **Do not
  auto-prune yet.**
- **What we *can* establish analytically:** fan-out never *saves* tokens — it spends `(N-1)·F`
  extra (F = per-agent spawn floor) to buy ~N× wall-clock. Slice-packing recovers that `(N-1)·F`
  whenever wall-clock isn't the priority. So the epic's "default to sequential + pack small slices"
  direction is sound *directionally* regardless of the exact F.

## Q1 — Per-agent fixed overhead

No runtime measurement possible (see TL;DR). Static floor, estimated at ~4 chars/token:

| Component (loaded when a `software-engineer` agent runs) | ~tokens |
|---|---:|
| `software-engineer.md` system prompt | ~1,960 |
| build cadence instructions injected by orchestrator (upper bound = full `build/SKILL.md`) | ≤~11,800 |
| `static-self-heal.md` (complex-step review only) | ~3,150 |
| `failure-routing.md` (per repair iteration) | ~600 |

The static instruction floor is only part of the story. **Two larger, unmeasured costs dominate:**

1. **Base-context cache-creation on every fresh agent.** A `main` session in this repo's ledger
   pays **108k–143k tokens of `cache_creation`** for base system prompt + tool schemas + CLAUDE.md
   + MCP instructions. A subagent's base is smaller, but it *re-pays a cache-creation floor on
   spawn* — and this is the number we have no subagent measurement for.
2. **The explore-before-editing phase.** Each agent independently runs codegraph/repowise/grep +
   file reads before its first edit. This is the variable priming cost the epic's "shared context
   pack" idea targets, and it is exactly what a real fan-out build must be metered to quantify.

**Conclusion:** F (the spawn floor) is real and non-trivial but currently unquantified. Treat
`F ≈ base-context cache-creation + static instruction floor + re-exploration` and **measure it** in
the prerequisite slice.

## Q2 — Spawn break-even

Analytic, pending F. A slice earns its own worktree only when its productive work `W_i` is large
relative to `F` **and** wall-clock matters. When `W_i << F` (a tiny slice), a separate agent spends
mostly floor — packing it into an already-primed agent is strictly cheaper on tokens. First-cut
rule to validate once F is measured: **pack any slice whose estimated work (steps × complexity
weight) is below ~F; fan out only slices above it.**

## Q3 — Fan-out cost multiplier

Analytic model for a wave of N independent slices:

- **Parallel (own worktree each):** `Σ Wᵢ + N·F`
- **Sequential / packed (one primed context):** `Σ Wᵢ + F` (roughly — one floor, shared)

So fan-out's **token penalty ≈ (N-1)·F**, bought in exchange for ~N× wall-clock. Fan-out **never
reduces tokens**; it only trades them for latency. This confirms the `SKILL.md:150` "~N×" claim is
directionally right for the *productive* work but understates it — the floor is re-paid N times too.
The exact multiplier needs the measured F.

## Q4 — Review-value no-op rates

Aggregated all available `review-value.jsonl` (2 projects, **10 records total**):

- by complexity: standard 7, complex 3 — by outcome: **fixed 7, no-op 3** — all at slice checkpoint
- per-lens hit rate: `spec-compliance-review` 2/4 (50%); **every other lens 100%** (1–2 dispatches each)

The near-uniform 100% is a **sampling artifact** — only slices that produced findings were logged,
so lenses look maximally valuable by construction. **This sample cannot justify pruning any lens.**

**Recommendation:** do not auto-prune. Keep collecting; revisit at **N ≥ ~100 records** with no-op
rate broken out by step complexity and by whether the diff touched the lens's domain (a security
lens's no-op rate on non-security diffs is the real prune signal, and it isn't captured at this
volume).

## Recommended threshold per epic slice

| Epic slice | Threshold from this spike |
|---|---|
| Default sequential / opt-in fan-out | **Adopt now** — analytically sound independent of F. |
| Slice-packing cost model | **Unblocked** — F is measurable now via `cost_meter report --json` (and, after #1513, from the durable log). Measure F on a representative fan-out build, then set the pack-below-F cutoff. |
| Shared context pack | Justified in principle (re-exploration is per-agent); size the win from the measured re-exploration component of F (same meter). |
| Diff-gated / cheap-first review | **Adopt now** — gate dispatch on diff domain regardless of Q4 data. |
| Auto-prune lenses from review-value | **Do not adopt.** Sample too small/biased; revisit at N≥100. |

## Prerequisite slice — RESOLVED

**`chore: meter per-subagent token usage during fan-out builds`** (#1513) was filed on the mistaken
premise that the cost meter could not attribute per-subagent tokens. It can — #1094 already did.
#1513 was narrowed at build-time to its one real gap: persisting `cache_creation_input_tokens` (the
F component) in the durable `cost-metering.jsonl` so F is legible from the log, not only from
`cost_meter report --json`. The slice-packing and shared-context-pack slices are **not blocked** —
F is measurable now.
