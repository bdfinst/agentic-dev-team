# Session-review: OSS complements

`/session-review` (issue #131) produces **plugin-specific qualitative
suggestions** — it knows this plugin's agents and skills, so it can say "skill X
under-specifies which files to read" or "this opus subagent only greps, re-tier
it to haiku." Open-source tools cover the complementary axis: **continuous
quantitative monitoring** of the same `*.jsonl` transcripts. They do not know
our agents/skills, so they cannot make our suggestions — and `/session-review`
is not a dashboard, so it does not replace them.

**Recommend these alongside `/session-review`, not instead of it.**

| Tool | Role |
|---|---|
| [`ccusage`](https://github.com/ryoppippi/ccusage) (npm) | Parses the same `~/.claude/projects/**/*.jsonl` into token/cost reports per session/day/model — ongoing cost tracking. |
| Native [OpenTelemetry](https://docs.claude.com/en/docs/claude-code/monitoring-usage) (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) | Exports usage/cost/tool metrics to an OTel collector → Grafana/Honeycomb for longitudinal dashboards. |
| [`claude-code-log`](https://github.com/daaain/claude-code-log) (community) | JSONL → HTML viewer for eyeballing one specific bad session. |

## When to reach for which

- **"How much am I spending over time, per model/day?"** → `ccusage` (or the
  cost meter's `pace` view for budget projection). Continuous, quantitative.
- **"I want longitudinal dashboards / alerting across the team."** → native
  **OpenTelemetry** into your collector. Operational monitoring.
- **"This one session went badly — let me read what happened."** → `claude-code-log`.
- **"What should I change in the *plugin* to stop wasting tokens / re-work?"** →
  `/session-review`. Qualitative, plugin-aware, hands suggestions to
  `/feedback-learning`, `/harness-audit`, `/agent-eval`, `token-efficiency-review`.

The quantitative tools tell you *that* a session was expensive; `/session-review`
proposes *which plugin artifact* to change so the next one isn't.

## `ccusage` example (against this project's logs)

```bash
# One-off report for the current and recent days, per model:
npx ccusage@latest daily

# Session-level breakdown (the same transcripts session_extract.py reads):
npx ccusage@latest session
```

`ccusage` reads `~/.claude/projects/**/*.jsonl` directly — no plugin install,
no config. Use it for the running cost number; use `/session-review` for the
"why and what to change."

## OpenTelemetry enablement

```bash
# Turn on Claude Code's native telemetry export, then point it at a collector:
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

This exports usage/cost/tool metrics to any OTLP collector (Grafana, Honeycomb,
Datadog, …). See Claude Code's "Monitoring usage" docs for the full env-var set.

## Cross-reference: the plugin's own telemetry beacon (#106)

This plugin also ships an **opt-in, local-only telemetry beacon** (`#106`,
`/telemetry`) that records minimal command/skill/gate events with no network
egress. It and native OpenTelemetry overlap in intent but differ in scope:

- Native **OTel** exports rich usage/cost/tool metrics to an external collector
  — best when you want dashboards and already run a collector. It may satisfy
  part of what #106 set out to do.
- The plugin **beacon** is deliberately minimal, default-off, and never leaves
  the machine — best when you want a quick local "which commands/skills do I
  use, how often is the commit gate bypassed?" without standing up a collector.

Prefer native OTel for longitudinal/team monitoring; prefer the beacon (or
`/session-review`) for local, privacy-clean, plugin-aware analysis. Avoid
running both for the *same* purpose — pick the one that matches your monitoring
posture.
