# Model and effort decision log

Per-agent record of the Haiku 5.5 re-evaluation (issues #2250, #2251). Agent frontmatter stays the single source of truth for current values ([ADR 0026](adr/0026-adopt-native-model-effort-agent-frontmatter-retire-the-band-resolver.md)); this log records the decision and evidence for each assignment.

## Feasibility findings (2026-10-08)

- Alias resolved: claude-haiku-5-5 (`claude -p --model haiku` reports `modelUsage` key `claude-haiku-5-5`).
- Effort variable: yes (`claude -p --effort <level>` accepted at `low` and `high`).
- Pricing: `plugins/dev-team/knowledge/model-pricing.json` now prices `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens) and `claude-sonnet-5-5` ($2 / $10), and the `haiku` alias points to `claude-haiku-5-5`.
- Evidence limit: evidence cells are self-reported text. The test checks format only; the run ID is not verified against an artifact.
