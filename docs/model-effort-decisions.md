# Model and effort decision log

Per-agent record of the Haiku 5.5 re-evaluation (issues #2250, #2251). Agent frontmatter stays the single source of truth for current values ([ADR 0026](adr/0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)); this log records the decision and evidence for each assignment.

## Feasibility findings (2026-10-08)

- Candidates evaluated: 0
- Alias resolved: claude-haiku-5-5 (`claude -p --model haiku` reports `modelUsage` key `claude-haiku-5-5`).
- Effort variable: yes (`claude -p --effort <level>` accepted at `low` and `high`).
- Pricing: `plugins/dev-team/knowledge/model-pricing.json` now prices `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens) and `claude-sonnet-5-5` ($2 / $10), and the `haiku` alias points to `claude-haiku-5-5`.
- Evidence limit: evidence cells are self-reported text. The test checks format only; the run ID is not verified against an artifact.

correctness-review recall gap is known and unfixed; its results are excluded from evidence.

## Decisions

| Agent | Source | Baseline model | Baseline effort | Final model | Final effort | Decision | Fixtures | Evidence | Projected saving |
|---|---|---|---|---|---|---|---|---|---|
| a11y-review | plugins/dev-team/agents/a11y-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| adr-author | plugins/dev-team/agents/adr-author.md | sonnet | high | sonnet | high | keep | - |  |  |
| ai-provenance-review | plugins/dev-team/agents/ai-provenance-review.md | opus | high | opus | high | keep | - |  |  |
| angular-reactivity-review | plugins/dev-team/agents/angular-reactivity-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| arch-review | plugins/dev-team/agents/arch-review.md | opus | high | opus | high | keep | - |  |  |
| architect | plugins/dev-team/agents/architect.md | opus | high | opus | high | keep | - |  |  |
| autoship-batch-proposer | plugins/dev-team/agents/autoship-batch-proposer.md | haiku | low | haiku | low | keep | - |  |  |
| claude-setup-review | plugins/dev-team/agents/claude-setup-review.md | haiku | high | haiku | high | keep | - |  |  |
| codebase-recon | plugins/dev-team/agents/codebase-recon.md | opus | high | opus | high | keep | - |  |  |
| component-architecture-review | plugins/dev-team/agents/component-architecture-review.md | haiku | high | haiku | high | keep | - |  |  |
| concurrency-review | plugins/dev-team/agents/concurrency-review.md | haiku | high | haiku | high | keep | - |  |  |
| correctness-review | plugins/dev-team/agents/correctness-review.md | opus | high | opus | high | keep | - |  |  |
| data-flow-tracer | plugins/dev-team/agents/data-flow-tracer.md | sonnet | high | sonnet | high | keep | - |  |  |
| doc-review | plugins/dev-team/agents/doc-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| domain-review | plugins/dev-team/agents/domain-review.md | opus | high | opus | high | keep | - |  |  |
| gherkin-quality-critic | plugins/dev-team/agents/gherkin-quality-critic.md | sonnet | high | sonnet | high | keep | - |  |  |
| js-fp-review | plugins/dev-team/agents/js-fp-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| mutation-kill | plugins/dev-team/agents/mutation-kill.md | opus | high | opus | high | keep | - |  |  |
| naming-review | plugins/dev-team/agents/naming-review.md | sonnet | high | sonnet | high | keep | - |  |  |
| orchestrator | plugins/dev-team/agents/orchestrator.md | sonnet | high | sonnet | high | keep | - |  |  |
| performance-review | plugins/dev-team/agents/performance-review.md | haiku | high | haiku | high | keep | - |  |  |
| plan-review-acceptance | plugins/dev-team/agents/plan-review-acceptance.md | sonnet | high | sonnet | high | keep | - |  |  |
| plan-review-design | plugins/dev-team/agents/plan-review-design.md | sonnet | high | sonnet | high | keep | - |  |  |
| plan-review-parallelization | plugins/dev-team/agents/plan-review-parallelization.md | sonnet | high | sonnet | high | keep | - |  |  |
| plan-review-strategic | plugins/dev-team/agents/plan-review-strategic.md | sonnet | high | sonnet | high | keep | - |  |  |
| plan-review-ux | plugins/dev-team/agents/plan-review-ux.md | sonnet | high | sonnet | high | keep | - |  |  |
| platform-engineer | plugins/dev-team/agents/platform-engineer.md | sonnet | high | sonnet | high | keep | - |  |  |
| product-manager | plugins/dev-team/agents/product-manager.md | sonnet | high | sonnet | high | keep | - |  |  |
| progress-guardian | plugins/dev-team/agents/progress-guardian.md | haiku | high | haiku | high | keep | - |  |  |
| qa-engineer | plugins/dev-team/agents/qa-engineer.md | sonnet | high | sonnet | high | keep | - |  |  |
| quality-reviewer | plugins/dev-team/agents/quality-reviewer.md | sonnet | high | sonnet | high | keep | - |  |  |
| react-reactivity-review | plugins/dev-team/agents/react-reactivity-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| refactor-opportunity-review | plugins/dev-team/agents/refactor-opportunity-review.md | haiku | high | haiku | high | keep | - |  |  |
| security-engineer | plugins/dev-team/agents/security-engineer.md | opus | high | opus | high | keep | - |  |  |
| security-review | plugins/dev-team/agents/security-review.md | opus | high | opus | high | keep | - |  |  |
| session-analysis | plugins/dev-team/agents/session-analysis.md | sonnet | high | sonnet | high | keep | - |  |  |
| software-engineer | plugins/dev-team/agents/software-engineer.md | sonnet | high | sonnet | high | keep | - |  |  |
| spec-compliance-review | plugins/dev-team/agents/spec-compliance-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| spec-reviewer | plugins/dev-team/agents/spec-reviewer.md | haiku | high | haiku | high | keep | - |  |  |
| structure-review | plugins/dev-team/agents/structure-review.md | sonnet | high | sonnet | high | keep | - |  |  |
| tech-writer | plugins/dev-team/agents/tech-writer.md | sonnet | high | sonnet | high | keep | - |  |  |
| test-review | plugins/dev-team/agents/test-review.md | sonnet | high | sonnet | high | keep | - |  |  |
| test-smell-review | plugins/dev-team/agents/test-smell-review.md | sonnet | high | sonnet | high | keep | - |  |  |
| token-efficiency-review | plugins/dev-team/agents/token-efficiency-review.md | haiku | high | haiku | high | keep | - |  |  |
| ui-ux-designer | plugins/dev-team/agents/ui-ux-designer.md | sonnet | high | sonnet | high | keep | - |  |  |
| vue-reactivity-review | plugins/dev-team/agents/vue-reactivity-review.md | haiku | medium | haiku | medium | keep | - |  |  |
| co-evolution-audit | plugins/dev-team/skills/co-evolution-audit/SKILL.md | n/a | low | n/a | low | keep | - |  |  |
| autoship | plugins/dev-team/skills/autoship/SKILL.md | n/a | medium | n/a | medium | keep | - |  |  |
