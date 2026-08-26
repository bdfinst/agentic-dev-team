# Wave / Review-Agent Fan-Out Consolidation

Soft guidance for keeping a single review wave's agent count within a coordination budget. Advisory only — it never blocks dispatch and adds no new gate.

## When it applies

When a single wave's agent-selection would dispatch **5 or more** review agents in one wave — whether the Inline Review Checkpoint dispatch table in `${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#inline-review-checkpoint` or Step 2 of `agents/quality-reviewer.md` selected them — note it in the phase/review output as a coordination-cost signal, not a hard block. Each agent already returns a small structured result, so the context-pollution risk is mitigated; what remains unmeasured is the coordination cost of aggregating many independent verdicts and driving one fix loop across potentially-overlapping finding sets.

## Why five

Martin Fowler's ["The Orchestrator's Tax"](https://martinfowler.com/articles/orchestrator-tax.html) recommends 2–4 concurrent agents per wave as a default and consolidating rather than scaling past ~5. `DEV_TEAM_MAX_PARALLEL_BUILDS` already bounds *hardware* concurrency (`min(16, cores-2)`, `scripts/build_jobs.py`); this guideline adds the missing *cognitive*/coordination ceiling. A single commit touching JS/TS + tests + API surface + domain logic + UI routinely selects 8–9 agents (`complexity-review`, `naming-review`, `js-fp-review`, `test-review`, `security-review`, `domain-review`, `a11y-review`, `structure-review`, `component-architecture-review`) — well past the budget.

## What to do

- **Surface, don't block.** Emit a one-line note in the phase/review output — e.g. `wave fan-out: 9 agents selected (>5 coordination-cost threshold)`. Dispatch proceeds unchanged.
- **Batch high-overlap agents.** Where two agents' scopes already overlap on the same lines, run them as a single combined pass instead of two. `structure-review` (baseline, every change) and `naming-review` frequently flag the same lines; `complexity-review` overlaps `structure-review` on nesting and function size. Combining an overlapping pass cuts verdict-aggregation and fix-loop overhead without losing coverage.
- **Prefer the higher-altitude rollup.** Strategic and test-design requests already consolidate into a `qa-engineer` / `/test-design` rollup rather than firing many per-file agents (see `agents/orchestrator.md` § Test-review request routing). Apply the same instinct wherever a rollup skill already exists.

## What this is not

Not a gate. It changes no dispatch behavior, blocks nothing, and adds no new metric or hook. It is a documented instinct for the orchestrator and quality-reviewer to weigh coordination cost when a wave's agent count is high — the cognitive analogue of the hardware ceiling `DEV_TEAM_MAX_PARALLEL_BUILDS` already provides.
