# Session-review: OSS complements

`/session-review` (issue #131) produces **plugin-specific qualitative
suggestions**. It knows this plugin's agents and skills, so it can say "skill X
under-specifies which files to read" or "this opus subagent only greps, re-tier
it to haiku." Open-source tools cover the complementary axis: **continuous
quantitative monitoring** of the same `*.jsonl` transcripts. They do not know
this plugin's agents and skills, so they cannot make these suggestions. `/session-review`
is not a dashboard, so it does not replace them.

Use these tools alongside `/session-review`, not instead of it.

| Tool | Role |
|---|---|
| [`ccusage`](https://github.com/ryoppippi/ccusage) (npm) | Parses the same `~/.claude/projects/**/*.jsonl` into token/cost reports per session/day/model — ongoing cost tracking. |
| Native [OpenTelemetry](https://docs.claude.com/en/docs/claude-code/monitoring-usage) (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) | Exports usage/cost/tool metrics to an OTel collector → Grafana/Honeycomb for longitudinal dashboards. |
| [`claude-code-log`](https://github.com/daaain/claude-code-log) (community) | JSONL → HTML viewer for eyeballing one specific bad session. |

## When to reach for which

- **"How much am I spending over time, per model or day?"** → `ccusage` (or the
  cost meter's `pace` view for budget projection). Continuous, quantitative.
- **"I want longitudinal dashboards and alerting across the team."** → native
  **OpenTelemetry** into your collector. Operational monitoring.
- **"This one session went badly — let me read what happened."** → `claude-code-log`.
- **"What should I change in the *plugin* to stop wasting tokens or re-work?"** →
  `/session-review`. Qualitative, plugin-aware, hands suggestions to
  `/feedback-learning`, `/harness-audit`, `/agent-eval`, `token-efficiency-review`.

The quantitative tools tell you *that* a session was expensive; `/session-review`
proposes *which plugin artifact* to change so the next session is cheaper.

## `ccusage` example (against this project's logs)

```bash
# One-off report for the current and recent days, per model:
npx ccusage@latest daily

# Session-level breakdown (the same transcripts session_report.py reads):
npx ccusage@latest session
```

`ccusage` reads `~/.claude/projects/**/*.jsonl` directly. It needs no plugin install
and no config. Use it for the running cost number. Use `/session-review` for the
"why and what to change."

## OpenTelemetry enablement

```bash
# Turn on Claude Code's native telemetry export, then point it at a collector:
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

This setting exports usage, cost, and tool metrics to any OTLP collector (Grafana, Honeycomb,
Datadog, and others). See Claude Code's "Monitoring usage" docs for the full env-var set.

## Cross-reference: the plugin's own telemetry beacon (#106)

This plugin also ships an **opt-in, local-only telemetry beacon** (`#106`,
`/telemetry`). The beacon records minimal command, skill, and gate events with no network
egress. It and native OpenTelemetry overlap in intent but differ in scope:

- Native **OTel** exports rich usage, cost, and tool metrics to an external collector.
  Use it when you want dashboards and already run a collector.
- Native OTel may satisfy part of what #106 set out to do.
- The plugin **beacon** is deliberately minimal, default-off, and never leaves
  the machine. Use it when you want a quick local answer to "which commands and skills do I
  use, and how often is the commit gate bypassed?" without standing up a collector.

Prefer native OTel for longitudinal and team monitoring. Prefer the beacon (or
`/session-review`) for local, privacy-clean, plugin-aware analysis. Avoid
running both for the *same* purpose. Pick the one that matches your monitoring
posture.
