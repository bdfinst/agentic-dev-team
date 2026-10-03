# Session-review harness (#131)

`/session-review` mines **ground-truth Claude Code session transcripts**
(`~/.claude/projects/<slug>/*.jsonl`) to suggest plugin improvements that reduce
**re-work**, cut **token usage**, and improve **accuracy**.

It fills a blind spot. The plugin already measures quality from two angles. Both
have gaps:

- `/agent-eval` + `evals/` grade agents on a *synthetic* fixture corpus. This proves
  an agent *can* detect a planted issue. It says nothing about real behavior.
- `/harness-audit` + `.claude/metrics/` analyze effectiveness from *self-reported*
  task logs. These logs are sparse and hold only what the model chose to record about itself.

Neither reads what *actually happened*: per-turn token usage, tool errors,
failed edits, user corrections, and skill and agent attribution. `/session-review`
does.

## Three stages (the model never reads raw transcripts)

| Stage | Component | What it does |
|---|---|---|
| 1. Extract | `${CLAUDE_PLUGIN_ROOT}/scripts/session_report.py --profile maintainer` (#127, #2046) | Deterministic, **zero model tokens**. Distills MBs of JSONL into a KB digest capturing all four signal classes equally (token / rework / accuracy / utilization). Privacy: metrics only — never prompt or code content. |
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
`metrics/session-digest.jsonl`. The path is deliberately left bare, because /session-review's own
scratch-state writer is out of scope for the #1406 `.claude/`-scoped artifact
migration. This stream is the real-session counterpart to the self-reported
`.claude/metrics/*-task-log.jsonl` streams. It lets `/harness-audit`
consume ground-truth data alongside the task logs. This section is the canonical
description of both the record schema and the harness-audit join.
[`eval-system.md`](eval-system.md) links here.

### Record schema (`session-digest/v2`)

Each line is a JSON object with **aggregate counts only** — no file names,
prompts, command strings, or code (privacy by construction):

| Field | Meaning |
|---|---|
| `recorded_at` | UTC ISO-8601 of the run (the only wall-clock field) |
| `sessions` | distinct sessions covered (subagents share their parent's session, so they do not inflate it) |
| `transcripts` / `subagent_transcripts` | main-thread sessions vs dispatched agent runs |
| `tokens` | input/output/cache token totals |
| `cost_usd`, `cache_hit_ratio` | session cost and cache-read efficiency |
| `token.by_agent_type` | per-agent token buckets keyed by agent name — `main`, `unattributed` where none resolves, `sidechain` for an older harness's inlined turns. **Was a bare message count before #2010**, which read as a token figure under this key and was off from `token.totals` by orders of magnitude |
| `rework` | counts: `failed_edits`, `repeated_file_edits`, `retried_bash_commands`, `repeated_verify_runs`, `permission_denials`, `compaction_events` |
| `accuracy` | `tool_calls`, `tool_error_rate`, `user_correction_turns` |
| `utilization` | `skills_invoked`, `agents_invoked` (RUNS), `agent_dispatches` (Agent/Task calls), `never_observed_skills`, `never_observed_agents` |

**v1 records are not comparable to v2** (#1994). Before v2 the extractor
globbed only `<project>/<sessionId>.jsonl`. Every dispatched agent's own
transcript went unread, so its tokens, tool calls, and rework were missing
entirely. On the machine that motivated this change, the gap was about a third of the tokens and
nearly half the cost. `retried_bash_commands` and `repeated_verify_runs` also
changed basis. The extractor now counts them within one thread of execution rather than
per session. Subagents share their parent's `sessionId`, and a
session-keyed tally scored a review panel's siblings running one command each
as retries. A trend stream holding both eras must split them on `schema`.

### harness-audit consumption (the join)

`/harness-audit` historically read only the self-reported
`.claude/metrics/*-task-log.jsonl`. It now joins real-session data by reading
`metrics/session-digest.jsonl`:

- **token and cost trends** → corroborate or contradict self-reported efficiency
  claims. The audit's blind spot was that it saw only self-reports.
- **`utilization.never_observed_*`** → flag stale or undiscoverable harness surface
  for the simplification recommendations harness-audit already makes.
- **`rework` / `accuracy` trends** → evidence for re-tiering or prompt fixes.

Join key: correlate by `recorded_at` time window. The two streams live at
different roots: `metrics/session-digest.jsonl` is deliberately bare, and
`.claude/metrics/*-task-log.jsonl` is migrated (see the note above). The
session-digest stream is ground truth. The task-log stream is self-reported.
Where they disagree, prefer the session digest.

## Downstream extraction (no monorepo checkout)

`/session-review`'s core steps (Extract, Analyze, and Suggest above) now run from
any installed plugin. `session_report.py --profile maintainer` ships
inside the plugin package, closing #1779 at the root (#2046/#2047). Only
two OPT-IN paths still require this monorepo's own dev checkout:
`--cross-machine` sync and rollup, and the raw-log semantic tier it gates. Both are
deliberately self-referential to this marketplace repo's own cross-machine
telemetry database (ADR 0032 Category 2). A downstream
install has no such database.

A downstream user of the plugin may have no access to this repo. That user may want to hand the maintainer their own session data for analysis without
running `/session-review`'s own orchestrated flow. For this case, use the sibling
`--profile downstream`: `${CLAUDE_PLUGIN_ROOT}/scripts/session_report.py
--profile downstream`. It ships inside the plugin package, so it is present
after a normal `claude plugin install`. It runs from a bare `python3` with no
dependencies. It writes ONE metrics-only JSON file for the current
project, an explicit `--project <path>`, or `--all-projects` for every
project the plugin has been used in on that machine. The privacy stance matches
everything else in this doc: counts, ratios, and names only, never prompt text,
code, or command strings. The user sends the resulting file to the
maintainer (for example, over MS Teams). The script has no network code
and never transmits anything on its own.

### Report schema (`downstream-session-report/v4`)

Alongside the main-thread session at `<project>/<sessionId>.jsonl`, every
dispatched agent writes its own transcript under
`<project>/<sessionId>/subagents/` (a Workflow's agents nest one level deeper
still). The extractor reads both. Two fields distinguish the two signals a reader will
otherwise conflate:

**`--plugin-version VERSION` and its coverage (#2018).** This flag scopes the report
to sessions whose project recorded `VERSION` in its own
`.claude/metrics/boundary-events.jsonl`. Attribution is best-effort. A session that never
dispatched anything through a hook that stamps `session_id` cannot be
attributed, so the report excludes it. The report does not drop those sessions silently.
Its top-level `version_filter_coverage` field (non-null only when
`--plugin-version` was passed) names `requested_version`,
`sessions_considered`, `sessions_attributed`,
`sessions_attributed_other_version` (a resolvable version, but not the
requested one; this is the filter working as intended, not a data gap), and
`sessions_unattributed` (no resolvable version at all). See
`knowledge/telemetry-schema.md`'s "Version-filtered downstream report
coverage" note for the full contract. The exclusion behavior itself is
unchanged. Only its visibility is new.

| Field | Meaning |
|---|---|
| `transcripts` / `subagent_transcripts` | main-thread sessions vs dispatched agent runs, both scoped to the reported window |
| `token.by_agent_type` | **per-agent token buckets** (#2010), keyed by agent name — `main` for the main thread, `unattributed` where no agent is resolvable. Same vocabulary as cost-metering's `by_agent_type` (`knowledge/telemetry-schema.md`) and now the same field names as its buckets; deliberately NOT `by_subagent`, which means main-vs-sidechain in the maintainer profile |

Each `token.by_agent_type` bucket carries:

| Key | Meaning |
|---|---|
| `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | the usage fields that make up what a dispatch **carried in** |
| `output_tokens` | what it generated — tracked, but deliberately outside `context_tokens` |
| `context_tokens` | the sum of the three context fields. Session telemetry puts ~90% of spend here, which is why this is the figure a panel-cost decision reads |
| `messages` | assistant messages carrying usage — the value this key held on its own before #2010 |
| `dispatches` | runs, counted one per subagent transcript. Never inferred from message volume, which would make a verbose agent look cheap per dispatch |
| `context_per_dispatch` | `context_tokens / dispatches`, or **`null`** when `dispatches` is 0 (`main`, and any agent that never ran). Null rather than 0 so a never-dispatched agent cannot sort as the cheapest row |

**Reconciliation invariant.** The per-agent `context_tokens` sum exactly to `token.totals`' three context fields. Both come from the same usage records, so a mismatch means a dispatch was double-counted or dropped. `tests/scripts/test_extract_session_report.py` pins this invariant.

**Not comparable across the #2010 boundary.** A pre-#2010 digest carries an int here. The cross-project merge preserves such a label at zero. It does not sum a message count into a token total.
| `utilization.agents_invoked` | agent RUNS, from each subagent transcript's `attributionAgent` — ground truth |
| `utilization.agent_dispatches` | `Agent`/`Task` tool calls, i.e. dispatches requested |

The extractor recognizes transcripts by DEPTH. Any `.jsonl` directly in a project
directory is a main-thread session whatever its name, while below
`subagents/` only `agent-<id>.jsonl` counts.
The harness writes bookkeeping alongside them (`subagents/workflows/<runId>/journal.jsonl`).
This file is not a transcript, so the extractor skips it. A Workflow's agents carry
`attributionAgent: "workflow-subagent"`, a harness role rather than an agent name.
Their tokens count, but they land in `unattributed` rather than inventing an agent.

Every string that becomes a report key passes a strict name filter. The extractor aggregates anything
that fails the filter under `other`. Report keys come from transcripts this
script does not author. A cloned repo's own `.claude/agents/*.md` chooses
`attributionAgent`. The script therefore enforces the "names, never full paths" guarantee at the
output boundary rather than trusting each input site.

`rework` answers at two scopes, deliberately. `retried_bash_commands` and
`repeated_verify_runs` are per thread of execution (one transcript). `repeated_file_edits`, `failed_edits`, `permission_denials`, and `compaction_events`
remain project-wide. A bash retry is a property of one agent's loop. A file is
shared state.

Runs and dispatches legitimately differ. A dispatch made from inside another
agent appears only in that agent's own transcript. A dispatch whose
transcript is absent never ran. `agents_invoked` falls back to dispatch counts
for a tree written by an older harness that produced no subagent transcripts.

**v1 reports are not comparable to v2.** Before v2 (issue #1990) the extractor
globbed only the main-thread layout. Subagent tokens, tool calls, and runs
were missing entirely. On the report that surfaced the bug, the gap was 41% of total spend.
`retried_bash_commands` and `repeated_verify_runs` also changed basis in v2.
They still carry the v1 (project-wide, session-keyed) basis in `session-digest/v1`
above. The same names are not comparable across the two artifacts until #1994
lands.
The extractor now counts them within one thread of execution rather than across a whole
project. Subagents share their parent's `sessionId`, and a session-keyed
tally scores a review panel's siblings running one command each as retries.

## OSS complements (#130)

For continuous *quantitative* monitoring, use `ccusage`, native
OpenTelemetry, or `claude-code-log`. They cover what `/session-review` does not.
`/session-review` covers the plugin-specific *qualitative* suggestions they
cannot make, because they do not know this plugin's agents and skills. See
`session-review-oss-complements.md`.

## Child issues

- #127 — deterministic session-log extractor (now `session_report.py --profile maintainer`, #2046)
- #128 — `/session-review` skill + `session-analysis` agent + report
- #129 — trend digest persistence + harness-audit consumption
- #130 — document OSS complements
- #1990 — count subagent transcripts (`downstream-session-report/v2`)
