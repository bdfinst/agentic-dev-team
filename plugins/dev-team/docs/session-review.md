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
`metrics/session-digest.jsonl` (deliberately left bare — /session-review's own
scratch-state writer is out of scope for the #1406 `.claude/`-scoped artifact
migration) — the real-session counterpart to the self-reported
`.claude/metrics/*-task-log.jsonl` streams — so `/harness-audit` can
consume ground-truth data alongside the task logs. This is the canonical
description of both the record schema and the harness-audit join;
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
globbed only `<project>/<sessionId>.jsonl`, so every dispatched agent's own
transcript was unread and its tokens, tool calls and rework were missing
entirely — on the machine that motivated this, about a third of the tokens and
nearly half the cost. `retried_bash_commands` and `repeated_verify_runs` also
changed basis: they are counted within one thread of execution now rather than
per session, because subagents share their parent's `sessionId` and a
session-keyed tally scored a review panel's siblings running one command each
as retries. A trend stream holding both eras must split them on `schema`.

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

`/session-review`'s core steps (Extract/Analyze/Suggest above) now run from
any installed plugin — `session_report.py --profile maintainer` ships
inside the plugin package, closing #1779 at the root (#2046/#2047). Only
two OPT-IN paths still require this monorepo's own dev checkout:
`--cross-machine` sync/rollup and the raw-log semantic tier it gates — both
deliberately self-referential to this marketplace repo's own cross-machine
telemetry database (ADR 0032 Category 2), not something a downstream
install has a database for.

For a downstream user of the plugin who has no access to this repo but
wants to hand the maintainer their own session data for analysis without
running `/session-review`'s own orchestrated flow, use the sibling
`--profile downstream`: `${CLAUDE_PLUGIN_ROOT}/scripts/session_report.py
--profile downstream`. It ships inside the plugin package (so it's present
after a normal `claude plugin install`), runs from a bare `python3` with no
dependencies, and writes ONE metrics-only JSON file — for the current
project, an explicit `--project <path>`, or `--all-projects` for every
project the plugin has been used in on that machine. Same privacy stance as
everything else in this doc: counts/ratios/names only, never prompt text,
code, or command strings. The user sends the resulting file to the
maintainer themselves (e.g. over MS Teams); the script has no network code
and never transmits anything on its own.

### Report schema (`downstream-session-report/v4`)

Alongside the main-thread session at `<project>/<sessionId>.jsonl`, every
dispatched agent writes its own transcript under
`<project>/<sessionId>/subagents/` (a Workflow's agents nest one level deeper
still). Both are read. Two fields distinguish the two signals a reader will
otherwise conflate:

**`--plugin-version VERSION` and its coverage (#2018).** Scopes the report
to sessions whose project recorded `VERSION` in its own
`.claude/metrics/boundary-events.jsonl` (best-effort — a session that never
dispatched anything through a hook that stamps `session_id` can't be
attributed and is excluded). Rather than dropping those sessions silently,
the report's top-level `version_filter_coverage` field (non-null only when
`--plugin-version` was passed) names `requested_version`,
`sessions_considered`, `sessions_attributed`,
`sessions_attributed_other_version` (a resolvable version, just not the
requested one — the filter working as intended, not a data gap), and
`sessions_unattributed` (no resolvable version at all) — see
`knowledge/telemetry-schema.md`'s "Version-filtered downstream report
coverage" note for the full contract. The exclusion behavior itself is
unchanged; only its visibility is new.

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

**Reconciliation invariant.** The per-agent `context_tokens` sum exactly to `token.totals`' three context fields. Both are derived from the same usage records, so a mismatch means a dispatch was double-counted or dropped; `tests/scripts/test_extract_session_report.py` pins it.

**Not comparable across the #2010 boundary.** A pre-#2010 digest carries an int here. The cross-project merge preserves such a label at zero rather than summing a message count into a token total.
| `utilization.agents_invoked` | agent RUNS, from each subagent transcript's `attributionAgent` — ground truth |
| `utilization.agent_dispatches` | `Agent`/`Task` tool calls, i.e. dispatches requested |

Transcripts are recognised by DEPTH: any `.jsonl` directly in a project
directory is a main-thread session whatever it is named, while below
`subagents/` only `agent-<id>.jsonl` counts.
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

- #127 — deterministic session-log extractor (now `session_report.py --profile maintainer`, #2046)
- #128 — `/session-review` skill + `session-analysis` agent + report
- #129 — trend digest persistence + harness-audit consumption
- #130 — document OSS complements
- #1990 — count subagent transcripts (`downstream-session-report/v2`)
