# Session-review harness (#131)

`/session-review` mines **ground-truth Claude Code session transcripts**
(`~/.claude/projects/<slug>/*.jsonl`) to suggest plugin improvements that reduce
**re-work**, cut **token usage**, and improve **accuracy**.

It fills a blind spot. The plugin already measures quality from two angles, both
with gaps:

- `/agent-eval` + `evals/` grade agents on a *synthetic* fixture corpus — proves
  an agent *can* detect a planted issue, says nothing about real behaviour.
- `/harness-audit` + `.claude/metrics/` analyse effectiveness from *self-reported*
  task logs — sparse, and only what the model chose to record about itself.

Neither reads what *actually happened*: per-turn token usage, tool errors,
failed edits, user corrections, and skill/agent attribution. `/session-review`
does.

## Three stages (the model never reads raw transcripts)

| Stage | Component | What it does |
|---|---|---|
| 1. Extract | `scripts/session_extract.py` (#127) | Deterministic, **zero model tokens**. Distills MBs of JSONL into a KB digest capturing all four signal classes equally (token / rework / accuracy / utilization). Privacy: metrics only — never prompt or code content. |
| 2. Analyze | `agents/session-analysis.md` + `skills/session-review/SKILL.md` (#128) | A focused agent reads **only the digest** and maps aggregated patterns to probable *plugin* causes. |
| 3. Suggest | `.dev-team-reports/session-review-<date>.md` (#128) | Ranked recommendations, each tagged `{token \| rework \| accuracy}`, naming the target artifact and handing off — never auto-applying. |

## Hand-off, not auto-apply

| Suggestion | Handed to |
|---|---|
| Config / prompt / convention fix | `/feedback-learning` |
| Model/effort re-tuning | `/harness-audit` + the agent's `model:`/`effort:` frontmatter (ADR 0026) |
| New / changed detection rule | `/agent-eval` |
| Token-heavy skill / agent | `token-efficiency-review` |

## Trend persistence (#129)

Each run appends one metrics-only record to the append-only trend stream
`metrics/session-digest.jsonl` (deliberately left bare — /session-review's own
scratch-state writer is out of scope for the #1406 `.claude/`-scoped artifact
migration) — the real-session counterpart to the self-reported
`.claude/metrics/*-task-log.jsonl` streams — so `/harness-audit` can
consume ground-truth data alongside the task logs. This is the canonical
description of both the record schema and the harness-audit join;
[`eval-system.md`](eval-system.md) links here.

### Record schema (`session-digest/v1`)

Each line is a JSON object with **aggregate counts only** — no file names,
prompts, command strings, or code (privacy by construction):

| Field | Meaning |
|---|---|
| `recorded_at` | UTC ISO-8601 of the run (the only wall-clock field) |
| `sessions`, `transcripts` | how many sessions/transcripts the digest covered |
| `tokens` | input/output/cache token totals |
| `cost_usd`, `cache_hit_ratio` | session cost and cache-read efficiency |
| `rework` | counts: `failed_edits`, `repeated_file_edits`, `retried_bash_commands`, `repeated_verify_runs`, `permission_denials`, `compaction_events` |
| `accuracy` | `tool_calls`, `tool_error_rate`, `user_correction_turns` |
| `utilization` | counts of `skills_invoked`, `agents_invoked`, `never_observed_skills`, `never_observed_agents` |

### harness-audit consumption (the join)

`/harness-audit` historically read only the self-reported
`.claude/metrics/*-task-log.jsonl`. It joins real-session data by reading
`metrics/session-digest.jsonl`:

- **token / cost trends** → corroborate or contradict self-reported efficiency
  claims (the audit's blind spot was that it saw only self-reports).
- **`utilization.never_observed_*`** → flag stale/undiscoverable harness surface
  for the simplification recommendations harness-audit already makes.
- **`rework` / `accuracy` trends** → evidence for re-tiering or prompt fixes.

Join key: correlate by `recorded_at` time window (the two streams live at
different roots — `metrics/session-digest.jsonl` is deliberately bare,
`.claude/metrics/*-task-log.jsonl` is migrated — see the note above). The
session-digest stream is ground-truth; the task-log stream is self-reported —
where they disagree, prefer the session digest.

## Downstream extraction (no monorepo checkout)

`/session-review` is maintainer-only tooling for this monorepo — it refuses
to run outside an `agentic-dev-team` dev checkout (see the Pre-flight guard
in `skills/session-review/SKILL.md`). For a downstream user of the plugin who
has no access to this repo but wants to hand the maintainer their own
session data for analysis, use the shippable counterpart instead:
`scripts/extract_session_report.py`. It ships inside the plugin package (so
it's present after a normal `claude plugin install`), runs from a bare
`python3` with no dependencies, and writes ONE metrics-only JSON file — for
the current project, an explicit `--project <path>`, or `--all-projects` for
every project the plugin has been used in on that machine. Same privacy
stance as everything else in this doc: counts/ratios/names only, never
prompt text, code, or command strings. The user sends the resulting file to
the maintainer themselves (e.g. over MS Teams); the script has no network
code and never transmits anything on its own.

### Report schema (`downstream-session-report/v2`)

Alongside the main-thread session at `<project>/<sessionId>.jsonl`, every
dispatched agent writes its own transcript under
`<project>/<sessionId>/subagents/` (a Workflow's agents nest one level deeper
still). Both are read. Two fields distinguish the two signals a reader will
otherwise conflate:

| Field | Meaning |
|---|---|
| `transcripts` / `subagent_transcripts` | main-thread sessions vs dispatched agent runs, both scoped to the reported window |
| `token.by_agent_type` | message counts keyed by agent name — `main` for the main thread, `unattributed` where no agent is resolvable. Same vocabulary as cost-metering's `by_agent_type` (`knowledge/telemetry-schema.md`); deliberately NOT `by_subagent`, which means main-vs-sidechain in `session_extract.py` |
| `utilization.agents_invoked` | agent RUNS, from each subagent transcript's `attributionAgent` — ground truth |
| `utilization.agent_dispatches` | `Agent`/`Task` tool calls, i.e. dispatches requested |

Only transcript-shaped filenames are read (`<sessionId>.jsonl`, `agent-<id>.jsonl`).
The harness writes bookkeeping alongside them — `subagents/workflows/<runId>/journal.jsonl`
— which is not a transcript and is skipped. A Workflow's agents carry
`attributionAgent: "workflow-subagent"`, a harness role rather than an agent name;
their tokens count, but they land in `unattributed` rather than inventing an agent.

Every string that becomes a report key passes a strict name filter, and anything
failing it is aggregated under `other`. Report keys come from transcripts this
script does not author — a cloned repo's own `.claude/agents/*.md` chooses
`attributionAgent` — so the "names, never full paths" guarantee is enforced at the
output boundary rather than trusted at each input site.

`rework` answers at two scopes, deliberately: `retried_bash_commands` and
`repeated_verify_runs` are per thread of execution (one transcript), while
`repeated_file_edits`, `failed_edits`, `permission_denials` and `compaction_events`
remain project-wide. A bash retry is a property of one agent's loop; a file is
shared state.

Runs and dispatches legitimately differ: a dispatch made from inside another
agent appears only in that agent's own transcript, and a dispatch whose
transcript is absent never ran. `agents_invoked` falls back to dispatch counts
for a tree written by an older harness that produced no subagent transcripts.

**v1 reports are not comparable to v2.** Before v2 (issue #1990) the extractor
globbed only the main-thread layout, so subagent tokens, tool calls and runs
were missing entirely — on the report that surfaced the bug, 41% of total spend.
`retried_bash_commands` and `repeated_verify_runs` also changed basis in v2 —
and still carry the v1 (project-wide, session-keyed) basis in `session-digest/v1`
above, so the same names are not comparable across the two artifacts until #1994
lands:
they are now counted within one thread of execution rather than across a whole
project, because subagents share their parent's `sessionId` and a session-keyed
tally scores a review panel's siblings running one command each as retries.

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
- #1990 — count subagent transcripts (`downstream-session-report/v2`)
