# Session-review harness (#131)

`/session-review` mines **ground-truth Claude Code session transcripts**
(`~/.claude/projects/<slug>/*.jsonl`) to suggest plugin improvements that reduce
**re-work**, cut **token usage**, and improve **accuracy**.

It fills a blind spot. The plugin already measures quality from two angles, both
with gaps:

- `/agent-eval` + `evals/` grade agents on a *synthetic* fixture corpus — proves
  an agent *can* detect a planted issue, says nothing about real behaviour.
- `/harness-audit` + `metrics/` analyse effectiveness from *self-reported* task
  logs — sparse, and only what the model chose to record about itself.

Neither reads what *actually happened*: per-turn token usage, tool errors,
failed edits, user corrections, and skill/agent attribution. `/session-review`
does.

## Three stages (the model never reads raw transcripts)

| Stage | Component | What it does |
|---|---|---|
| 1. Extract | `scripts/session_extract.py` (#127) | Deterministic, **zero model tokens**. Distills MBs of JSONL into a KB digest capturing all four signal classes equally (token / rework / accuracy / utilization). Privacy: metrics only — never prompt or code content. |
| 2. Analyze | `agents/session-analysis.md` + `skills/session-review/SKILL.md` (#128) | A focused agent reads **only the digest** and maps aggregated patterns to probable *plugin* causes. |
| 3. Suggest | `reports/session-review-<date>.md` (#128) | Ranked recommendations, each tagged `{token \| rework \| accuracy}`, naming the target artifact and handing off — never auto-applying. |

## Hand-off, not auto-apply

| Suggestion | Handed to |
|---|---|
| Config / prompt / convention fix | `/feedback-learning` |
| Model re-tiering | `/harness-audit` + `.claude/model-overrides.json` |
| New / changed detection rule | `/agent-eval` |
| Token-heavy skill / agent | `token-efficiency-review` |

## Trend persistence (#129)

Each run appends a metrics-only record to `metrics/session-digest.jsonl` so
`/harness-audit` can consume real-session data alongside the self-reported task
logs. Schema and the harness-audit join are documented in
`eval-system.md` → "Session-review trend digest".

## OSS complements (#130)

For continuous *quantitative* monitoring, reach for `ccusage`, native
OpenTelemetry, or `claude-code-log` — they cover what `/session-review` does not.
`/session-review` covers the plugin-specific *qualitative* suggestions they
cannot, since they don't know this plugin's agents and skills. See
`session-review-oss-complements.md`.

## Child issues

- #127 — deterministic session-log extractor (`scripts/session_extract.py`)
- #128 — `/session-review` skill + `session-analysis` agent + report
- #129 — trend digest persistence + harness-audit consumption
- #130 — document OSS complements
