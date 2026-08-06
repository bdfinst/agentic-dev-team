# 35. Defer two-lane generation/validation concurrency in `mutation-kill --all` (#1909)

Date: 2026-08-05

## Status

Accepted

## Context

Issue #1909 (Slice 4 of epic #1905) asked whether `mutation-kill`'s
`--all --concurrency <n>` mode should decouple two resource classes that
appear coupled 1:1 per worktree slot:

- **generation** — LLM-bound, one `claude --print` headless call per round,
  network/token-limited, negligible local CPU;
- **validation** — CPU/memory-bound, a scoped Stryker mutation run plus a
  `dotnet build` and a scoped `dotnet test`.

The premise came from an external manual mutation-kill pass that credited
roughly half its per-batch wall-clock reduction to pipelining these two
lanes: dispatch the next batch of generation sub-agents while the previous
batch's validation is still draining, instead of `generate → barrier → wait
for all validation → generate next`. Their reported figure: ~4h of
test-writing idle per batch, cut roughly in half after pipelining. The issue
explicitly required confirming today's actual behavior before designing, and
sanctioned deferral as an outcome.

### What today's code actually does

Three findings materially change the question, all read from the current
tree:

**1. `--concurrency` is prose, not code.** No script in the repo accepts a
`--concurrency` (or `--jobs`) flag for multi-file worktree fan-out.
`stryker_shard_pipeline.py`'s `build_parser()` declares only `shards`,
`--repo-root`, `--stryker-bin`, `--model`, `--max-rounds`, `--skip-agent`,
`--skip-existing`, `--max-age-hours`. `--concurrency` and `--parallel` exist
only as instructions to the `mutation-kill` agent in
`plugins/dev-team/agents/mutation-kill.md` — and `mutation-kill.md` says so
of `--parallel` outright ("this fan-out is an agent-orchestration step
(spawning generation sub-agents), not a scripted one"). There is no slot
bookkeeping, no worktree pool, and no scheduler to split. **A "coupled 1:1
per slot" invariant is a description of what an agent naturally does when
following the prose, not a property enforced anywhere in code.**

**2. The one implemented multi-file path is deliberately sequential, and it
already releases the worktree before the LLM phase.**
`stryker_shard_pipeline.run_all` is documented as "Process every shard
**sequentially** (compounding depends on ordering)". Inside `process_shard`
the ordering is `worktree_add` → `run_shard_stryker` → `worktree_remove` (in
a `finally`) → `launch_survivor_fix`. The survivor-fix loop — the entire
LLM-bound phase — runs *after* the worktree is torn down, from `repo_root`,
so fixes commit onto `HEAD` and compound into the next shard. No worktree
slot sits idle waiting on an LLM call on this path. The specific waste the
issue hypothesized does not exist in the code that exists.

**3. The per-file loop is already pipelined at round granularity, which is
the shape the source doc migrated *to*.** `mutation_kill_loop.run_for_file`
drives `_run_round` one round at a time: `_score_round` (Stryker, CPU) →
`generate` (LLM) → `apply_generated_methods` → `_verify_and_commit` (build +
scoped test + commit). Generation for round N+1 *cannot* start before round
N's report exists — the survivor list is its input. That dependency is
causal, not a scheduling artifact. There is no batch barrier to remove: the
external pass's ~4h idle was `O(a whole batch's generation time)` blocked on
`O(a whole batch's validation)`; ours is at most `O(one round's generation)`
per in-flight file, already interleaved.

### The upside is bounded by an unmeasured ratio

Decoupling cannot shorten a single file's critical path (it is causal). Its
only lever is raising *files in flight* while holding peak concurrent
validations at the machine's safe ceiling. With `f = g / (g + v)` the
generation share of a round's wall-clock, that ceiling gives a maximum
speedup of `1 / (1 - f) = (g + v) / v`. Reaching the source doc's ~2× needs
`f ≈ 0.5` — generation costing as much wall-clock as a scoped Stryker run
plus a `dotnet build` plus a scoped `dotnet test`. That is implausible on
its face, but **nobody has measured `f` in this repo**, and the issue's own
step 2 says "Quantify before committing to a build." The speedup is also
*purchased* with a proportional rise in concurrent LLM calls — i.e. token
burn rate — which cuts directly against the plugin's established fan-out
convention (`build_jobs.py`: `min(--jobs, DEV_TEAM_MAX_PARALLEL_BUILDS, wave
width)`, sequential by default, opt-in only, because "fan-out never *saves*
tokens, it trades them for wall-clock", #1515).

### Most of the asked-for capability is already reachable with existing dials

`--concurrency` already scales files in flight up to `cores − 2` (default
2), and `--parallel` already over-provisions generation *relative to*
validation within one file's Phase-4 survivor set, without worktrees,
"because test-file writes don't conflict with source-file reads". Those two
dials plus Stryker's own `--stryker-concurrency` already require a dedicated
"Concurrency cross-reference" section in `mutation-kill.md` to keep them
apart. A generation-lane/validation-lane pair would be dials four and five.

## Decision

**Defer.** Do not build two-lane (decoupled generation/validation)
concurrency for `mutation-kill --all` now. `mutation-kill.md`'s documented
flags, defaults, and `--concurrency`/`--parallel` semantics are unchanged by
this decision.

Deferral is conditional, not permanent. The measurement that would flip it:
instrument a real `--all` run to split per-round wall-clock between
`generate()` and `_score_round`'s Stryker run plus `_verify_and_commit`'s
build/test. **If generation is ≥ 35% of per-round wall-clock** (max speedup
≥ ~1.5×) on a representative repo, revisit this ADR. Below that, the ceiling
is under 1.5× for a Large, resource-exhaustion-risky redesign bought with
extra token burn.

### Alternatives rejected, with reasons

| Alternative | Why rejected |
| --- | --- |
| **A1. Full two-pool scheduler** — separate generation and validation pools with a handoff queue | Requires first *building* the single-pool multi-file driver that does not exist (`--concurrency` is prose), so the true cost is "write the scheduler, then split it". Upside capped at `1/(1-f)` with `f` unmeasured. Reintroduces a serialization barrier exactly where the decoupling was meant to remove one: fixes commit onto `HEAD`, and concurrent commits from N worktrees contend on the repo's index — the current sequential design sidesteps that by construction. Adds two dials to a three-dial surface that already needs a disambiguation section. |
| **A2. Speculative prefetch** — generate the next file's round-1 tests while the current file validates | Only round 1 is prefetchable: rounds ≥ 2 need the prior round's report, so the win is roughly `f / rounds`, a fraction of an already-bounded `f`. And it *wastes* the scarce resource: a file that converges at round 1, or hits generation exhaustion / a model downgrade, throws generated tokens away. Per #1515 the scarce resource is token spend, not wall-clock. |
| **A3. Raise the `--concurrency` default above 2** | This is precisely the resource-exhaustion risk #1909 flags (the source pass saw `concurrency:5` go SIGSEGV-prone at 16GB). It also *forfeits* round-1 baseline reuse, which `mutation-kill.md` scopes to "`--concurrency 1` only (or omitted)" because each worktree does not share the main checkout's `StrykerOutput/` — so it can be a net loss, not just a risk. The operator can already raise it deliberately per machine. |

## Consequences

**Not gained:** `--all` throughput stays bounded by the operator's
`--concurrency` choice, with each in-flight file's generation and validation
phases serialized by their own causal dependency. On a run where generation
is a large share of round wall-clock, some slot-time is idle. The size of
that loss is unknown, by admission.

**Avoided:** A Large redesign whose payoff is capped by an unmeasured ratio;
a commit-serialization barrier that would have to be reintroduced at the
handoff point; two additional concurrency dials on an interface that already
needs a cross-reference section to keep three apart; and a default-path
increase in concurrent LLM calls that the plugin's own fan-out convention
(#1515) says must be opt-in and reported, never implicit.

**Premise corrected for the next reader:** the "1:1 coupled worktree slot"
framing does not describe code that exists. `--concurrency` is agent prose;
the implemented `stryker_shard_pipeline.py` path is sequential by design and
tears the worktree down *before* the LLM-bound survivor-fix phase. A future
session must not re-derive this from the gap analysis's read of the docs.

**Higher-leverage lever identified, not committed here:** if `--all`
throughput becomes the real pain, the validation side looks like the better
investment than lane-splitting — notably extending round-1 baseline reuse to
`--concurrency > 1` by materializing the baseline report into each worktree,
which removes a redundant scoped Stryker run per file with no new
concurrency dial and no new resource risk. Recorded as a triage candidate
only; no issue is filed and no work is scheduled by this ADR.

**Boundary of the evidence:** no wall-clock measurement of `g` versus `v`
was taken. The bounded-upside argument is structural (`1/(1-f)` under a
fixed validation ceiling) plus a qualitative read of what each phase does;
it is not an empirical result and should not be quoted as one. The
`.git`-index contention argument for A1 is likewise reasoned from git's
serialization of index operations, not from an observed failure.

## References

- Issue #1909 — the design pass this ADR records
- Epic #1905 — batch this slice belongs to
- Issue #1912 — spec (AC2: implement-or-defer is a genuine open decision)
- ADR 0020 — folding the mutation pipeline into the plugin as scripted mechanics
- ADR 0030 — mutation baseline reuse (ancestor check)
- Issue #1515 — fan-out is opt-in; it trades tokens for wall-clock
- `plugins/dev-team/agents/mutation-kill.md` — "Parallelism" (with its
  "Sub-agent fan-out within a file (`--parallel`)" and "Interaction with
  `--concurrency`" subsections), "Concurrency cross-reference", "Baseline
  reuse for Round 1 (`--concurrency 1` only)"
- `plugins/dev-team/skills/mutation-testing/scripts/stryker_shard_pipeline.py`
  — `run_all` (sequential), `process_shard` (worktree released before
  `launch_survivor_fix`)
- `plugins/dev-team/skills/mutation-testing/scripts/mutation_kill_loop.py` —
  `run_for_file` / `_run_round` / `_score_round` / `_verify_and_commit`
- `plugins/dev-team/scripts/build_jobs.py` — the `min(--jobs,
  DEV_TEAM_MAX_PARALLEL_BUILDS, wave width)` convention
- Issue #1753 / #1757 — precedent for closing a slice via a recorded
  deferral decision rather than an implementation
