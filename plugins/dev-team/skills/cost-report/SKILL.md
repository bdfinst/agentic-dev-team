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
  Bash(python3 *, jq *, tail *, cat *, ls *)
---

# Cost Report (#102)

Role: worker. Reports runtime cost/token spend captured by the cost meter.

Token usage is not available to hooks, so the `Stop`/`SubagentStop` hook
(`hooks/cost-meter.sh`) records a per-session summary to
`metrics/cost-metering.jsonl` by parsing the session transcript, converting
tokens to dollars via `knowledge/model-pricing.json`. This skill reports that
data.

## Steps

1. **Per-session breakdown.** If the user passes `--transcript <path>` (or you
   know the current transcript path), run an exact per-agent report:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py report --transcript <path>
   ```

   Otherwise show the most recently recorded session from the metrics log:

   ```bash
   tail -n 1 metrics/cost-metering.jsonl | python3 -m json.tool
   ```

2. **Regression check.** Compare the latest session's total cost against the
   rolling mean of prior sessions (default tolerance +50%):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py regression \
     --log metrics/cost-metering.jsonl --tolerance 0.5
   ```

3. Report the per-agent, per-command, and per-fix-loop-iteration tokens + cost,
   the session total, and whether a cost regression was detected. Do not invent
   numbers — print exactly what the meter emits. If `metrics/cost-metering.jsonl`
   is absent, tell the user the meter hasn't recorded a session yet (the hook
   records on turn end).

   For a windowed cost-regression baseline (mean of only the N most recent prior
   sessions instead of all-time), pass `--window N`:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py regression \
     --log metrics/cost-metering.jsonl --tolerance 0.5 --window 10
   ```

## Attribution dimensions (#102, #170)

`report` breaks spend down by **model** and by **thread** (main-loop vs
subagent), plus the session **total**.

Attribution is limited to what the Claude Code harness actually records on
transcript turns. Per-command, per-phase, and per-fix-loop-iteration buckets
were **removed** (#170): they relied on `attributionSkill` / `orchestrationPhase`
/ `fixLoopIteration` fields the harness never writes (verified 0/312 in a real
transcript), and a plugin has no write-path into the transcript — so those
dimensions were always empty. The main/subagent split uses the native
`isSidechain` flag, which the harness does provide.

## Privacy boundary

The meter persists **only** token counts, dollar amounts, model identifiers, and
the main/subagent thread flag — never prompt text, code, file paths, or tool
payloads. `metrics/cost-metering.jsonl` is a metrics-only artifact by
construction.

1. **Account pace (optional, #142).** When the user asks "am I on track for my
   budget", "how much have I burned this week", or "which model should I use for
   the rest of the period", report account-level pace: cumulative spend over a
   rolling window, the implied daily rate, and the projected spend for a billing
   period — flagging when pace would exhaust a stated budget:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py pace \
     --log metrics/cost-metering.jsonl --budget 100 --period-days 30 --window-days 7
   ```

   Without `--budget` it reports pace only (no flag). When it flags an
   over-budget pace it suggests dropping a model tier (Opus→Sonnet) for the rest
   of the window.

## Notes

- Disable the meter with `DEV_TEAM_COST_METER=off`.
- Pricing lives in `knowledge/model-pricing.json` — update it when rates change
  (it is the named instrument for every cost number this skill prints).
