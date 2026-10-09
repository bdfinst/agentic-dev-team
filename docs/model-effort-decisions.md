# Model and effort decision log

Per-agent record of the Haiku 5.5 re-evaluation (issues #2250, #2251). Agent frontmatter stays the single source of truth for current values ([ADR 0026](adr/0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)); this log records the decision and evidence for each assignment.

## Feasibility findings (2026-10-08)

- Candidates evaluated: 7
- Alias resolved: claude-haiku-5-5
- Alias check: `claude -p --model haiku` reports `modelUsage` key `claude-haiku-5-5`.
- Effort variable: yes
- Effort check: `claude -p --effort <level>` accepted at `low` and `high`, and effort changes cost: in the `concurrency-review` run (see Notes) `medium` cost $0.132 and `high` cost $0.168 for the same 49 trials per arm.
- Pricing: `plugins/dev-team/knowledge/model-pricing.json` now prices `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens; the `claude-api` skill pricing table lists Claude Haiku 5.5 at those rates) and the `haiku` alias points to `claude-haiku-5-5`. `claude -p` resolves `opus` to `claude-opus-5-5` and `sonnet` to `claude-sonnet-5-5` (checked 2026-10-09, including an `opus` and a `sonnet` agent), so those aliases and rates ($4 / $20 and $2 / $10) were added too.
- Evidence limit: evidence cells are self-reported text. The test checks format only; the run ID is not verified against an artifact.

correctness-review recall gap is known and unfixed; its results are excluded from evidence.

## Method

A/B per candidate, run outside `/agent-eval`: each fixture in `evals/expected` that names the agent and is a single file (directory fixtures count in `Fixtures` but are not run), 3 trials per arm (5 for the five agents re-run with tools; see Notes). Baseline arm = current frontmatter, candidate arm = proposed model/effort, same session. Each run is `claude -p --model <m> --effort <e>` with the agent definition as the system prompt and the fixture file inline, with no tools for the tool-less rows and with tools for the five re-run agents (`scripts/model_effort_ab.py`); output is graded by `scripts/eval_grade.py`. Evidence is therefore not directly comparable to `evals/baseline.json`, which `/agent-eval` produces.

A downgrade rule is relative to the current tier: the proposed tier must have recall equal to or better than the current tier, no increase in clean-fixture false positives, and 100% parse. `delta:0` in an evidence cell means the proposed tier lost no recall relative to the current tier, not that every trial passed.

Cost is the USD the CLI reported, summed over all trials of one arm, not a figure computed from `model-pricing.json`. `Eval cost saving (USD)` is the baseline arm's cost minus the candidate arm's; it measures the eval run, not a forecast of production spend. `Fixtures` counts every fixture naming the agent; `directory fixtures only` means none could be run by this harness.

## Notes

- Every tool-bearing downgrade candidate that a tool-less run had passed (`concurrency-review`, `js-fp-review`, `naming-review`, `test-smell-review`, `token-efficiency-review`) was re-run with the tool-enabled harness (`scripts/model_effort_ab.py`) at 5 trials per fixture; their results replace the earlier tool-less evidence. A downgrade needs recall equal to or better than the current tier, no clean-fixture false-positive increase, and 100% parse. The re-runs used the already-applied (proposed) tier as the artifact's `baseline` arm, so artifact arm labels are reversed relative to this table's Baseline and Final columns.
- `concurrency-review` (haiku/high to haiku/medium), run `20261009T120538Z-concurrency-review-haiku-high-4c89`: medium passed 48, failed 1, FP 1, cost 0.132; high passed 46, failed 3, FP 0, cost 0.168. The clean-fixture false positive rose, so reason `failed eval`; stays haiku/high keep. The run stopped at the cost cap with 98 of 100 trials (49 of 50 per arm).
- `js-fp-review` (haiku/medium to haiku/low), run `20261009T122901Z-js-fp-review-haiku-medium-9363`: low passed 31, failed 14, FP 0, cost 0.126; medium passed 29, failed 16, FP 0, cost 0.146. No recall lost, so the downgrade holds. Both arms fail about one third of trials, so the fixtures or the grader are worth a look.
- `naming-review` (sonnet/high to haiku/high), run `20261009T124756Z-naming-review-sonnet-high-5e84`: haiku passed 10, FP 10, cost 0.249; sonnet passed 17, FP 10, cost 2.572. Recall fell, so reason `failed eval`; stays sonnet/high keep.
- `test-smell-review` (sonnet/high to haiku/high), run `20261009T132115Z-test-smell-review-sonnet-high-d4d5`: haiku passed 10 with 1 parse failure, FP 1, cost 0.089; sonnet passed 11, FP 1, cost 1.077. Parse and recall both failed, so reason `failed eval`; stays sonnet/high keep.
- `token-efficiency-review` (haiku/high to haiku/medium), run `20261009T134443Z-token-efficiency-review-haiku-high-5b08`: medium passed 4, failed 21, FP 7, cost 0.108; high passed 4, failed 21, FP 6, cost 0.156. The clean-fixture false positives rose, so reason `failed eval`; stays haiku/high keep. Both arms pass 4 of 25 trials, so the fixtures or the grader need a look.
- `structure-review` (sonnet/high to haiku/high): candidate passed 27 of 30 trials; three `st-duplicate-code` trials returned unparseable JSON. Reason `failed eval`; stays keep.
- `data-flow-tracer`: candidate passed 9 of 9 at cost 0.239 to 0.027, but the agent traces code with tools the harness withheld. Reason `weak evidence: tools withheld`; stays keep.
- `claude-setup-review`: fixtures are directories, which the harness does not run. Stays keep.
- `not selected`: the agent has 3 or more fixtures but was not run (`a11y-review`, `component-architecture-review`, `doc-review`, `progress-guardian`, `refactor-opportunity-review`). Candidate selection ranks eligible agents by projected saving and caps the count; the run capped candidates at 8 (issue #2250). Seven candidates were evaluated. All five already run on `haiku`, so only an effort downgrade was possible. This log does not record the per-agent ranking, so `not selected` means untested, not disproven.
- `evals/model-effort/runs/20261008T213541Z-doc-review-haiku-low-8569.json` is a harness smoke run, not a candidate evaluation. `doc-review` stays `not selected`.
- `opus: not run`: opus agents, including the high-stakes set (`correctness-review`, `security-review`), were not run. `correctness-review` results would also carry its known recall gap.
- `harness gap: Phase 0 not reproduced`: `test-review` was not run because its Phase 0 mechanical pre-phase is not reproduced by this harness.
- A blank reason is accepted only on a keep row with fewer than 3 fixtures.

## Decisions

| Agent | Source | Baseline model | Baseline effort | Final model | Final effort | Decision | Fixtures | Evidence or reason | Eval cost saving (USD) |
|---|---|---|---|---|---|---|---|---|---|
| a11y-review | plugins/dev-team/agents/a11y-review.md | haiku | medium | haiku | medium | keep | 3 | not selected |  |
| adr-author | plugins/dev-team/agents/adr-author.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| ai-provenance-review | plugins/dev-team/agents/ai-provenance-review.md | opus | high | opus | high | keep | 2 | insufficient fixtures |  |
| angular-reactivity-review | plugins/dev-team/agents/angular-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| arch-review | plugins/dev-team/agents/arch-review.md | opus | high | opus | high | keep | 2 | insufficient fixtures |  |
| architect | plugins/dev-team/agents/architect.md | opus | high | opus | high | keep | 0 | no fixture |  |
| autoship-batch-proposer | plugins/dev-team/agents/autoship-batch-proposer.md | haiku | low | haiku | low | keep | 0 | no fixture |  |
| claude-setup-review | plugins/dev-team/agents/claude-setup-review.md | haiku | high | haiku | high | keep | 6 | directory fixtures only |  |
| codebase-recon | plugins/dev-team/agents/codebase-recon.md | opus | high | opus | high | keep | 0 | no fixture |  |
| component-architecture-review | plugins/dev-team/agents/component-architecture-review.md | haiku | high | haiku | high | keep | 3 | not selected |  |
| concurrency-review | plugins/dev-team/agents/concurrency-review.md | haiku | high | haiku | high | keep | 10 | failed eval |  |
| correctness-review | plugins/dev-team/agents/correctness-review.md | opus | high | opus | high | keep | 12 | opus: not run |  |
| data-flow-tracer | plugins/dev-team/agents/data-flow-tracer.md | sonnet | high | sonnet | high | keep | 3 | weak evidence: tools withheld |  |
| doc-review | plugins/dev-team/agents/doc-review.md | haiku | medium | haiku | medium | keep | 6 | not selected |  |
| domain-review | plugins/dev-team/agents/domain-review.md | opus | high | opus | high | keep | 5 | opus: not run |  |
| gherkin-quality-critic | plugins/dev-team/agents/gherkin-quality-critic.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| js-fp-review | plugins/dev-team/agents/js-fp-review.md | haiku | medium | haiku | low | downgrade | 9 | eval:20261009T122901Z-js-fp-review-haiku-medium-9363; model:claude-haiku-5-5; effort:low; fixtures:9; trials:5; delta:0; cost:0.146->0.126 | 0.020 |
| mutation-kill | plugins/dev-team/agents/mutation-kill.md | opus | high | opus | high | keep | 0 | no fixture |  |
| naming-review | plugins/dev-team/agents/naming-review.md | sonnet | high | sonnet | high | keep | 6 | failed eval |  |
| orchestrator | plugins/dev-team/agents/orchestrator.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| performance-review | plugins/dev-team/agents/performance-review.md | haiku | high | haiku | high | keep | 1 | insufficient fixtures |  |
| plan-review-acceptance | plugins/dev-team/agents/plan-review-acceptance.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-design | plugins/dev-team/agents/plan-review-design.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-parallelization | plugins/dev-team/agents/plan-review-parallelization.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-strategic | plugins/dev-team/agents/plan-review-strategic.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| plan-review-ux | plugins/dev-team/agents/plan-review-ux.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| platform-engineer | plugins/dev-team/agents/platform-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| product-manager | plugins/dev-team/agents/product-manager.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| progress-guardian | plugins/dev-team/agents/progress-guardian.md | haiku | high | haiku | high | keep | 3 | not selected |  |
| qa-engineer | plugins/dev-team/agents/qa-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| quality-reviewer | plugins/dev-team/agents/quality-reviewer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| react-reactivity-review | plugins/dev-team/agents/react-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| refactor-opportunity-review | plugins/dev-team/agents/refactor-opportunity-review.md | haiku | high | haiku | high | keep | 4 | not selected |  |
| security-engineer | plugins/dev-team/agents/security-engineer.md | opus | high | opus | high | keep | 0 | no fixture |  |
| security-review | plugins/dev-team/agents/security-review.md | opus | high | opus | high | keep | 6 | opus: not run |  |
| session-analysis | plugins/dev-team/agents/session-analysis.md | sonnet | high | sonnet | high | keep | 1 | insufficient fixtures |  |
| software-engineer | plugins/dev-team/agents/software-engineer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| spec-compliance-review | plugins/dev-team/agents/spec-compliance-review.md | haiku | medium | haiku | medium | keep | 1 | insufficient fixtures |  |
| spec-reviewer | plugins/dev-team/agents/spec-reviewer.md | haiku | high | haiku | high | keep | 0 | no fixture |  |
| structure-review | plugins/dev-team/agents/structure-review.md | sonnet | high | sonnet | high | keep | 12 | failed eval |  |
| tech-writer | plugins/dev-team/agents/tech-writer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| test-review | plugins/dev-team/agents/test-review.md | sonnet | high | sonnet | high | keep | 13 | harness gap: Phase 0 not reproduced |  |
| test-smell-review | plugins/dev-team/agents/test-smell-review.md | sonnet | high | sonnet | high | keep | 5 | failed eval |  |
| token-efficiency-review | plugins/dev-team/agents/token-efficiency-review.md | haiku | high | haiku | high | keep | 5 | failed eval |  |
| ui-ux-designer | plugins/dev-team/agents/ui-ux-designer.md | sonnet | high | sonnet | high | keep | 0 | no fixture |  |
| vue-reactivity-review | plugins/dev-team/agents/vue-reactivity-review.md | haiku | medium | haiku | medium | keep | 2 | insufficient fixtures |  |
| co-evolution-audit | plugins/dev-team/skills/co-evolution-audit/SKILL.md | n/a | low | n/a | low | keep | 0 | no fixture |  |
| autoship | plugins/dev-team/skills/autoship/SKILL.md | n/a | medium | n/a | medium | keep | 0 | no fixture |  |
