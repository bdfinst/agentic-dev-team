# Model and effort decision log

Per-agent record of the Haiku 5.5 re-evaluation (issues #2250, #2251). Agent frontmatter stays the single source of truth for current values ([ADR 0026](adr/0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)); this log records the decision and evidence for each assignment.

## Feasibility findings (2026-10-08)

- Candidates evaluated: 7
- Alias resolved: claude-haiku-5-5 (`claude -p --model haiku` reports `modelUsage` key `claude-haiku-5-5`).
- Effort variable: yes (`claude -p --effort <level>` accepted at `low` and `high`).
- Pricing: `plugins/dev-team/knowledge/model-pricing.json` now prices `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens) and `claude-sonnet-5-5` ($2 / $10), and the `haiku` alias points to `claude-haiku-5-5`.
- Evidence limit: evidence cells are self-reported text. The test checks format only; the run ID is not verified against an artifact.

correctness-review recall gap is known and unfixed; its results are excluded from evidence.

## Method

A/B per candidate: each fixture in `evals/expected` that names the agent and is a single file, 3 trials per arm, baseline arm = current frontmatter, candidate arm = proposed model/effort, same session. Each run is `claude -p --model <m> --effort <e>` with the agent definition as the system prompt, no tools, and the fixture file inline; output is graded by `scripts/eval_grade.py`. Cost is USD summed over all trials of one arm, from the CLI's reported cost. Limits: no tools, so agents that rely on repo exploration are weakly tested; directory fixtures are not run.

## Notes

- `structure-review` (sonnet/high to haiku/high): candidate passed 27 of 30 trials; three `st-duplicate-code` trials returned unparseable JSON. Stays keep.
- `data-flow-tracer`: candidate passed 9 of 9, but the agent traces code with tools the harness withheld. The evidence is real but weak, so it stays keep.
- `claude-setup-review`: fixtures are directories, which the harness does not run. Stays keep.
- Agents with 3 or more file fixtures that were not run (cap of 8 candidates, or opus/high-stakes) stay keep with their baseline.

## Decisions

| Agent | Source | Baseline model | Baseline effort | Final model | Final effort | Decision | Fixtures | Evidence | Projected saving |
|---|---|---|---|---|---|---|---|---|---|
| a11y-review | plugins/dev-team/agents/a11y-review.md | haiku | medium | haiku | medium | keep | 3 |  |  |
| adr-author | plugins/dev-team/agents/adr-author.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| ai-provenance-review | plugins/dev-team/agents/ai-provenance-review.md | opus | high | opus | high | keep | 2 | insufficient fixtures |  |
| angular-reactivity-review | plugins/dev-team/agents/angular-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| arch-review | plugins/dev-team/agents/arch-review.md | opus | high | opus | high | keep | 2 | insufficient fixtures |  |
| architect | plugins/dev-team/agents/architect.md | opus | high | opus | high | keep | 0 | no fixture |  |
| autoship-batch-proposer | plugins/dev-team/agents/autoship-batch-proposer.md | haiku | low | haiku | low | keep | 0 | no fixture |  |
| claude-setup-review | plugins/dev-team/agents/claude-setup-review.md | haiku | high | haiku | high | keep | 6 | no fixture |  |
| codebase-recon | plugins/dev-team/agents/codebase-recon.md | opus | high | opus | high | keep | 0 | no fixture |  |
| component-architecture-review | plugins/dev-team/agents/component-architecture-review.md | haiku | high | haiku | high | keep | 3 |  |  |
| concurrency-review | plugins/dev-team/agents/concurrency-review.md | haiku | high | haiku | high | keep | 10 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:medium; fixtures:10; trials:3; delta:0; cost:0.048->0.034 | 0.014 |
| correctness-review | plugins/dev-team/agents/correctness-review.md | opus | high | opus | high | keep | 12 |  |  |
| data-flow-tracer | plugins/dev-team/agents/data-flow-tracer.md | sonnet | high | sonnet | high | keep | 3 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:high; fixtures:3; trials:3; delta:0; cost:0.239->0.027 | 0.212 |
| doc-review | plugins/dev-team/agents/doc-review.md | haiku | medium | haiku | medium | keep | 6 |  |  |
| domain-review | plugins/dev-team/agents/domain-review.md | opus | high | opus | high | keep | 5 |  |  |
| gherkin-quality-critic | plugins/dev-team/agents/gherkin-quality-critic.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| js-fp-review | plugins/dev-team/agents/js-fp-review.md | haiku | medium | haiku | medium | keep | 9 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:low; fixtures:9; trials:3; delta:0; cost:0.040->0.035 | 0.005 |
| mutation-kill | plugins/dev-team/agents/mutation-kill.md | opus | high | opus | high | keep | 0 | no fixture |  |
| naming-review | plugins/dev-team/agents/naming-review.md | sonnet | high | sonnet | high | keep | 6 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:high; fixtures:6; trials:3; delta:0; cost:0.523->0.060 | 0.463 |
| orchestrator | plugins/dev-team/agents/orchestrator.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| performance-review | plugins/dev-team/agents/performance-review.md | haiku | high | haiku | high | keep | 1 | insufficient fixtures |  |
| plan-review-acceptance | plugins/dev-team/agents/plan-review-acceptance.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-design | plugins/dev-team/agents/plan-review-design.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-parallelization | plugins/dev-team/agents/plan-review-parallelization.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-strategic | plugins/dev-team/agents/plan-review-strategic.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-ux | plugins/dev-team/agents/plan-review-ux.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| platform-engineer | plugins/dev-team/agents/platform-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| product-manager | plugins/dev-team/agents/product-manager.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| progress-guardian | plugins/dev-team/agents/progress-guardian.md | haiku | high | haiku | high | keep | 3 |  |  |
| qa-engineer | plugins/dev-team/agents/qa-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| quality-reviewer | plugins/dev-team/agents/quality-reviewer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| react-reactivity-review | plugins/dev-team/agents/react-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| refactor-opportunity-review | plugins/dev-team/agents/refactor-opportunity-review.md | haiku | high | haiku | high | keep | 4 |  |  |
| security-engineer | plugins/dev-team/agents/security-engineer.md | opus | high | opus | high | keep | 0 | no fixture |  |
| security-review | plugins/dev-team/agents/security-review.md | opus | high | opus | high | keep | 6 |  |  |
| session-analysis | plugins/dev-team/agents/session-analysis.md | sonnet | high | sonnet | high | keep | 1 | insufficient fixtures |  |
| software-engineer | plugins/dev-team/agents/software-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| spec-compliance-review | plugins/dev-team/agents/spec-compliance-review.md | haiku | medium | haiku | medium | keep | 1 | insufficient fixtures |  |
| spec-reviewer | plugins/dev-team/agents/spec-reviewer.md | haiku | high | haiku | high | keep | 0 | no fixture |  |
| structure-review | plugins/dev-team/agents/structure-review.md | sonnet | high | sonnet | high | keep | 12 |  |  |
| tech-writer | plugins/dev-team/agents/tech-writer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| test-review | plugins/dev-team/agents/test-review.md | sonnet | high | sonnet | high | keep | 13 |  |  |
| test-smell-review | plugins/dev-team/agents/test-smell-review.md | sonnet | high | sonnet | high | keep | 5 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:high; fixtures:5; trials:3; delta:0; cost:0.396->0.038 | 0.358 |
| token-efficiency-review | plugins/dev-team/agents/token-efficiency-review.md | haiku | high | haiku | high | keep | 5 | eval:ab-2026-10-08; model:claude-haiku-5-5; effort:medium; fixtures:5; trials:3; delta:0; cost:0.055->0.039 | 0.016 |
| ui-ux-designer | plugins/dev-team/agents/ui-ux-designer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| vue-reactivity-review | plugins/dev-team/agents/vue-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| co-evolution-audit | plugins/dev-team/skills/co-evolution-audit/SKILL.md | n/a | low | n/a | low | keep | 0 | no fixture |  |
| autoship | plugins/dev-team/skills/autoship/SKILL.md | n/a | medium | n/a | medium | keep | 0 | no fixture |  |
