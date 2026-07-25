---
name: cost-report
description: >-
  Report actual token spend and dollar cost of dispatched work — per agent and
  total — and flag cost regressions. Use when the user asks "how much did that
  cost", "token spend", "cost of this run", "cost report", or wants to check for
  a cost regression after /code-review or an orchestration run.
argument-hint: "[--transcript <path>] [--tolerance <n>]"
user-invocable: true
allowed-tools: >-
  Bash(python3 *, jq *, tail *, cat *, ls *, test *)
---

# Cost Report (#102)

Role: worker. Reports runtime cost/token spend captured by the cost meter.

Token usage is not available to hooks, so the `Stop`/`SubagentStop` hook
(`hooks/cost_meter.py`) records a per-session summary to
`metrics/cost-metering.jsonl` by parsing the session transcript, converting
tokens to dollars via `knowledge/model-pricing.json`. This skill reports that
data.

## Steps

1. **Per-session breakdown.** If the user passes `--transcript <path>` (or you
   know the current transcript path), run an exact per-agent report:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py report --transcript <path>
   ```

   Otherwise show the most recently recorded session from the metrics log
   (prefer the migrated `.claude/metrics/` location, falling back to the
   legacy bare `metrics/` path for a project mid-transition):

   ```bash
   log=".claude/metrics/cost-metering.jsonl"; [ -f "$log" ] || log="metrics/cost-metering.jsonl"
   tail -n 1 "$log" | python3 -m json.tool
   ```

2. **Regression check.** Compare the latest session's total cost against the
   rolling mean of prior sessions (default tolerance +50%):

   ```bash
   log=".claude/metrics/cost-metering.jsonl"; [ -f "$log" ] || log="metrics/cost-metering.jsonl"
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py regression \
     --log "$log" --tolerance 0.5
   ```

3. Report the per-model, per-thread (main/subagent), and per-agent-type tokens
   + cost, the session total, and whether a cost regression was detected. Do
   not invent numbers — print exactly what the meter emits. If
   `.claude/metrics/cost-metering.jsonl` (or the legacy `metrics/cost-metering.jsonl`)
   is absent, tell the user the meter hasn't recorded a session yet (the hook
   records on turn end).

   For a windowed cost-regression baseline (mean of only the N most recent prior
   sessions instead of all-time), pass `--window N`:

   ```bash
   log=".claude/metrics/cost-metering.jsonl"; [ -f "$log" ] || log="metrics/cost-metering.jsonl"
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py regression \
     --log "$log" --tolerance 0.5 --window 10
   ```

## Attribution dimensions (#102, #170, #1094)

`report` breaks spend down by **model**, by **thread** (main-loop vs
subagent), and by **agent type** (#1094), plus the session **total**.

The agent-type dimension answers "which agent type drives spend" (e.g.
`security-review` vs `test-review` vs `general-purpose`): main-loop turns land
in `main`; sidechain turns are attributed via the native `attributionAgent`
field the harness stamps on subagent records, falling back to the Task/Agent
dispatch join (`tool_use` `input.subagent_type` paired with
`toolUseResult.agentId`). Sidechain spend carrying neither signal lands in an
honest `unattributed` bucket — the meter never guesses. The meter also folds in
the sibling per-subagent transcript files
(`<dir>/<session-id>/subagents/agent-*.jsonl`) that newer harness versions
write instead of inline sidechain turns, so subagent spend stays visible.

Attribution is limited to what the Claude Code harness actually records on
transcript turns. Per-command, per-phase, and per-fix-loop-iteration buckets
were **removed** (#170): they relied on `attributionSkill` / `orchestrationPhase`
/ `fixLoopIteration` fields the harness never writes (verified 0/312 in a real
transcript), and a plugin has no write-path into the transcript — so those
dimensions were always empty. The main/subagent split uses the native
`isSidechain` flag, which the harness does provide; the agent-type dimension
likewise reads only harness-recorded fields (verified against a real
transcript, #1094).

## Review value (#348)

`/build` records, per inline review checkpoint, whether review actually changed
anything (`metrics/review-value.jsonl`, schema in `performance-metrics`). When
that file exists, surface a compact "review value" summary so the user can see
whether the pipeline's review overhead paid off on this work — the count of
checkpoints that **found+fixed** a defect vs. those that **passed no-op**, with
the fix-loop iterations spent:

```bash
log=".claude/metrics/review-value.jsonl"; [ -f "$log" ] || log="metrics/review-value.jsonl"
[ -f "$log" ] && jq -s '
  {checkpoints: length,
   no_op:    (map(select(.outcome=="no-op"))    | length),
   fixed:    (map(select(.outcome=="fixed"))     | length),
   escalated:(map(select(.outcome=="escalated")) | length),
   issues_found: (map(.issues_found) | add // 0),
   issues_fixed: (map(.issues_fixed) | add // 0),
   fix_iterations: (map(.fix_iterations) | add // 0)}' \
  "$log"
```

A run that is mostly `no_op` is evidence the review ceremony is over-provisioned
for that class of work — feed it back into the `/plan` plan-tier and `/build`
per-step complexity routing. Counts only; no code or file content is stored.

## Privacy boundary

The meter persists **only** token counts, dollar amounts, model identifiers,
the main/subagent thread flag, and agent-type identifiers — never prompt text,
code, file paths, or tool payloads. `metrics/cost-metering.jsonl` is a
metrics-only artifact by construction.

1. **Account pace (optional, #142).** When the user asks "am I on track for my
   budget", "how much have I burned this week", or "which model should I use for
   the rest of the period", report account-level pace: cumulative spend over a
   rolling window, the implied daily rate, and the projected spend for a billing
   period — flagging when pace would exhaust a stated budget:

   ```bash
   log=".claude/metrics/cost-metering.jsonl"; [ -f "$log" ] || log="metrics/cost-metering.jsonl"
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py pace \
     --log "$log" --budget 100 --period-days 30 --window-days 7
   ```

   Without `--budget` it reports pace only (no flag). When it flags an
   over-budget pace it suggests dropping a model tier (Opus→Sonnet) for the rest
   of the window.

## Notes

- Disable the meter with `DEV_TEAM_COST_METER=off`.
- Pricing lives in `knowledge/model-pricing.json` — update it when rates change
  (it is the named instrument for every cost number this skill prints).
