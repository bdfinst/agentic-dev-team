---
name: orchestration-benchmark
description: >-
  Run the pre-registered solo-vs-coordinated A/B benchmark: three arms (solo
  session, current orchestration, delegation-only sweep) over the same task
  matrix at matched verification rigor, measuring dollar cost, token band
  shift, quality, rework, and wall-clock. Use when the user asks "is
  orchestration worth it", "benchmark the pipeline against a solo run",
  "measure delegation value", "orchestration benchmark", or wants the
  crossover threshold below which a solo session beats delegation.
argument-hint: "[--task-class <trivial|standard|complex>] [--runs <n>] [--dry-run]"
user-invocable: true
allowed-tools: >-
  Read, Grep, Glob, Write,
  Bash(python3 *, jq *, date *, mkdir *, ls *, tail *, cat *,
       command -v claude)
---

# Orchestration Benchmark (#1095)

Role: orchestrator. This command dispatches benchmark runs and aggregates
their results — it never performs the benchmark tasks itself and never edits
the code under test.

You have been invoked with the `/orchestration-benchmark` command.

> **Not `/benchmark`.** `/benchmark` measures **runtime performance of web
> pages** (Core Web Vitals, resource sizes, load times). This skill measures
> **orchestration value**: whether the dev-team pipeline's delegation earns
> its overhead against a solo session on the same task at the same rigor.
> Different subject, different instruments, different report.

## Orchestrator constraints

1. **Matched rigor is non-negotiable.** Every arm runs the identical task
   with **identical acceptance checks**. An arm may not skip or weaken
   verification — a cheap worker that reads less and passes weaker checks is
   a different product, not a cheaper version of the same one. A run that
   weakened its checks is a rigor violation: discard it, do not average it in.
2. **The protocol is pre-registered.** The decision rule below is fixed
   before the first run. Do not adjust thresholds, arms, or the task matrix
   after seeing results — report against the rule as written.
3. **Never report a single run.** Report median + spread per arm per task
   class. A difference smaller than the spread is a null result.
4. **Write results to files.** Per-run records and the final report go to
   files; present only the summary tables and verdict in chat.
5. **Be concise.** Tables and short sentences; no narration of each run.

## Parse Arguments

Arguments: $ARGUMENTS

- `--task-class <trivial|standard|complex>`: Run only one task-matrix class
  (bucket names from `knowledge/task-size-classifier.md`). Default: all three.
- `--runs <n>`: Runs per arm per task class (default: 5). Fewer than 5 makes
  the result **exploratory, not decidable** — say so in the report and do not
  apply the decision rule to it.
- `--dry-run`: Print the run plan — interleaved schedule, selected fixtures,
  each arm's agents' declared `model:`/`effort:` frontmatter, and a cost
  estimate — without dispatching anything.

## Arms (3, matched rigor)

| Arm | Configuration |
| --- | --- |
| **A — Solo** | Single session, no subagent dispatch; the session model does all reading and all work itself. |
| **B — Current orchestration** | The dev-team pipeline exactly as shipped. |
| **C — Delegation-only sweep** | Arm B plus the #1093 sweep rule: the orchestrator never reads beyond classification-sized probes; all bulk reading goes to low-band workers with scoped briefs per the #1092 batching rules. |

All three arms run the identical task with identical acceptance checks (the
fixture's eval assertions). See constraint 1: unequal rigor invalidates the
run.

## Task matrix

Sample across the `knowledge/task-size-classifier.md` buckets
(`trivial | standard | complex`) — one task class per bucket:

| Class | Bucket | Example | Expectation |
| --- | --- | --- | --- |
| Small single-file | `trivial` | One-file bug fix from an eval fixture | Expected **worst case** for delegation |
| Medium few-file | `standard` | Feature slice touching 3–5 files | Near the predicted crossover |
| Large sweep-heavy | `complex` | `/code-review` over a 20+ file diff; repo-wide audit | Expected **best case** for delegation |

Reuse existing `/agent-eval` fixtures under `evals/fixtures/` wherever
possible; add fixtures only where a class has none.

## Repetitions and isolation

- **≥5 runs per arm per task class** (see `--runs`). Report median + spread
  (min/max or IQR) — never a single run. A difference smaller than the spread
  is a null result.
- **Isolation via `/headless-run`** (`skills/headless-run/SKILL.md`): each run
  dispatches through
  `skills/headless-run/scripts/isolated_dispatch.py` — fresh session id,
  clean HOME and config dir, scrubbed env — so runs are independent and no
  parent-session identity or state carries over.
- **Cache parity: interleave arm order** — A, B, C, A, B, C, … Never batch
  all runs of one arm together; batching gives later arms warmer caches.
- **Model pinning:** record the exact model ID(s) per run. All arms dispatch
  the same agents, each resolved by the harness from its own `model:`/
  `effort:` frontmatter (ADR 0026) — record that frontmatter before the
  first run and include it in the report. If any dispatched agent's
  frontmatter changes mid-experiment, **abort and restart**; do not mix runs
  across frontmatter versions.

## Metrics (instrument named per metric)

| Metric | Instrument |
| --- | --- |
| Dollar cost & tokens by model/thread | `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py report --transcript <path>` |
| Tokens moved to low band (mechanism check) | The cost meter's `by_model` / `by_thread` split from the same report |
| Quality | The fixture's eval assertions — identical across arms |
| Rework | Fix-loop iterations; `.claude/metrics/review-value.jsonl` where review checkpoints ran |
| Wall-clock | Harness transcript timestamps |

### Mechanism check (mandatory)

Arm C's cost reduction must be produced by the claimed mechanism. If Arm C's
cost drops but reading tokens did **not** shift to low-band subagent threads
(the cost meter's `by_model`/`by_thread` split shows the movement), treat the
result as a **rigor violation, not a win** — the savings came from reading
less, not from delegating the reading.

## Decision rule (pre-registered — fixed before the first run)

Apply per task class:

1. **Adopt C over B** only if **all three** hold:
   - median cost reduction ≥ 25%;
   - no quality regression — every run passes the fixture's acceptance
     checks;
   - the mechanism check passes.
2. **Retain B over A** only if B beats A on cost **or** quality. If A
   dominates B on a class, **report it** — that finding feeds
   `/harness-audit` — do not suppress it.
3. **Crossover output:** report the task-size threshold below which A/B
   beats C. That number feeds the #1093 sweep rule.

## Threats to validity

Each of these must be explicitly addressed in the report — not silently
skipped:

1. **Unmatched rigor** — an arm passed weaker checks; the comparison is void.
2. **Fixed-overhead asymmetry** — orchestration pays a constant dispatch tax
   that dominates small tasks and vanishes on large ones.
3. **Cache warmth** — runs batched by arm give later arms warmer caches;
   interleaving (above) is the control, state whether it held.
4. **Model drift** — a dispatched agent's `model:`/`effort:` frontmatter or an underlying model changed
   mid-experiment; the abort/restart rule (above) is the control.
5. **Fixture overfitting** — the crossover threshold generalizes only as far
   as the task matrix; say so wherever the threshold is quoted.

## Report

Write the report to `.dev-team-reports/orchestration-benchmark-<date>.md`.

For the header block and closing Provenance section, follow
`knowledge/report-template.md`; the sections below are this skill's own
body.

Body sections, in order:

1. **Per-class results** — one table per task class: median + spread per arm
   for each metric (cost, tokens by band, quality pass rate, rework,
   wall-clock).
2. **Crossover threshold** — the task-size threshold below which A/B beats
   C, with the fixture-overfitting caveat attached.
3. **Decision-rule outcomes** — per class: adopt/retain verdicts against the
   pre-registered rule, including the mechanism-check result.
4. **Threats to validity** — all five items above, each with how this run
   addressed it.
5. **Run log** — each dispatched agent's declared `model:`/`effort:`
   frontmatter, exact model IDs per run, interleaved schedule as executed,
   discarded runs and why.

## Relationship to other tooling

- `/benchmark` is **runtime-performance-only** (web pages); this skill
  measures **orchestration value**. They share nothing but the name shape.
- `/headless-run` is the isolation mechanism for every dispatched run;
  `/agent-eval` fixtures supply the tasks and acceptance checks;
  `/cost-report` and `hooks/lib/cost_meter.py` are the cost instruments;
  each agent's `model:`/`effort:` frontmatter is the model-pinning source of
  truth (ADR 0026); `/harness-audit` consumes any "A dominates B" finding.
- **Instrumentation flip belongs to the run, not to this skill.** After the
  first full documented protocol run (#1099), the instrumentation list in
  `plugins/dev-team/CLAUDE.md` moves "efficiency gains" from *Not yet* to
  *Instrumented*, naming this skill as the instrument. Shipping this skill
  does not perform that flip.
