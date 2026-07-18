---
name: run-report
description: >-
  Report one orchestrated run's timeline — per-state dwell time, rejection
  count, hook denials/bypasses grouped by cause, and cost — joined from
  boundary-events.jsonl, cost-metering.jsonl, and workflow-states.jsonl for a
  given session_id (default: most recent). Use when the user asks "how did
  that run go", "show the run report", "/run-report", or wants a single view
  of a `/ship`/`/autoship`/`/build` run instead of cross-referencing streams
  by hand.
argument-hint: "[--session <id>]"
user-invocable: true
allowed-tools: >-
  Bash(python3 *, jq *, tail *, cat *, ls *, test *)
---

# Run Report (#1167)

Role: worker. Reports one `session_id`'s composed run timeline by joining the
existing deterministic metrics streams — no model tokens spent parsing
transcripts.

`workflow-states.jsonl` (#1166) records only state *transitions*; current
state and per-state dwell time are always derived by replay
(`hooks/lib/workflow_state.py::derive_current_state()` /
`compute_dwell_times()`). `boundary-events.jsonl` records every guard hook's
block/warn/bypass decision. `cost-metering.jsonl` records per-session token
spend, but is keyed by transcript filename, not `session_id` — see Join
limitations below.

## Steps

1. **Run the report.** If the user passes `--session <id>`, use it; otherwise
   let the library auto-detect the most recent `session_id` seen across
   `boundary-events.jsonl` and `workflow-states.jsonl`:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/run_report.py report --session <id>
   ```

2. **Present a readable summary, not raw JSON.** Render the JSON the library
   prints as a short table/summary:
   - `session_id` and `current_state`
   - a `dwell_seconds` table, one row per state
   - `rejection_count` and `bypass_count`
   - `denials_by_cause` as a table of `matched_rule -> count`
   - the `cost` section: if `joinable` is `false`, say so plainly and show
     `reason` plus the `most_recent_entry` (if any) labeled as a rough,
     unattributed proxy — never present it as this session's actual cost.

3. If a stream file is absent, its section is simply empty (zero counts, no
   dwell times) — that is not an error; say so rather than treating it as a
   failure.

## Join limitations

`cost-metering.jsonl` entries are written by the `Stop` hook
(`hooks/cost_meter.py` → `hooks/lib/cost_meter.py::cmd_record()`) keyed by
transcript filename — the hook never learns the session ID, so there is no
reliable per-session join key today. Rather than guess an attribution the
data doesn't support, the report marks `cost.joinable: false` and surfaces
only the most recent recorded entry as an unattributed reference point. A
future stream-schema change adding `session_id` to `cost-metering.jsonl`
would let this become a real join.

## Privacy boundary

This report composes only fields the underlying streams already document in
`knowledge/telemetry-schema.md` (rule IDs, counts, state names, token/dollar
totals) — never command text, prompt text, or file contents.
