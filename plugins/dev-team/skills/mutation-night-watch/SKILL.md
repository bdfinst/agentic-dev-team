---
name: mutation-night-watch
description: Launch, schedule, and hand off an unattended, LLM-free overnight mutation night-watch run. Use when the user wants a mutation-score baseline waiting each morning without paying LLM cost or blocking a session overnight, says "run mutation testing overnight", "schedule a nightly mutation scan", "set up a mutation night watch", or asks how to get an unattended mutation baseline. Wraps mutation_nightwatch.py — report-only measurement, never generation.
role: worker
user-invocable: true
allowed-tools: Read, Write, Bash(python3 *), Bash(launchctl *), Bash(crontab *), Bash(schtasks *)
---

# Mutation Night-Watch

Role: worker. Launches and schedules a report-only measurement run. It never
generates a test, never invokes an LLM, and never commits — that is the
`mutation-kill` agent's job, the next morning, reading this skill's output.

> **Naming note.** The skill is named `mutation-night-watch`; its underlying
> scripts, output directory (`reports/mutation-nightwatch/`), and launchd
> label use `mutation_nightwatch`/`mutation-nightwatch` — this is an
> intentional, stable naming split; do not rename the on-disk paths without a
> migration plan (#1856).

## Why this exists, and how it differs from `mutation-kill`

`mutation-kill` already has two modes: **interactive** (an agent generates
tests turn by turn) and **`--headless`** (unattended, but every round still
shells out to `claude --print` — LLM cost and API availability are both in
the loop). Neither mode is meant to run **overnight with nobody watching**:
a multi-hour unattended `claude --print` loop is expensive and, on a flaky
network, silently stalls.

Night-watch is a **third, LLM-free mode**: measurement only. It runs the real
mutation tool for each detected stack, scores the result with the same
[`mutation_report.py`](../mutation-testing/scripts/mutation_report.py) the
rest of the mutation-testing skill family uses, and writes the result where
`mutation-kill` (or a human) picks it up the next day. It does not replace
`mutation-kill`'s fixing modes — see [`mutation-testing/SKILL.md`](../mutation-testing/SKILL.md)
for those.

## Constraints

- **Report-only. Never generation.** The script
  ([`../mutation-testing/scripts/mutation_nightwatch.py`](../mutation-testing/scripts/mutation_nightwatch.py))
  has no code path that shells to an LLM. If a stack's tool run mutates a
  survivor count, that is the mutation tool itself running normally — nothing
  here writes a test.
- **Mechanical repair only, never code.** Before measuring, the script runs
  each stack's package-pin-sync step (`npm ci` when `node_modules` is
  missing, `dotnet restore`) so a stale dependency tree doesn't fail the
  whole run on a mechanical break. It never edits a production or test file,
  and never commits — see the script's `mechanical_repair`.
- **Detected-but-unscored stacks are reported, not guessed.** pitest (Java)
  and go-mutesting (Go) are detected but have no `mutation_report.py` parser
  yet; they show up in the summary as `skipped_no_parser`, never a
  fabricated score.
- **Always confirm scope before scheduling a recurring run.** A single ad hoc
  `--detach` launch needs no extra confirmation beyond what the user already
  asked for; wiring a scheduler entry (Task Scheduler / launchd / cron) that
  runs unattended on a recurring cadence is a standing change to the user's
  machine — confirm the schedule and scope before writing the scheduler
  config.

## Step 1: Detect and preview scope

Run once without `--detach` on a small scope, or just read the detection
output, before committing to an overnight run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/mutation-testing/scripts/mutation_nightwatch.py" --repo-root . --no-sleep-inhibit
```

This prints the run directory and writes `MORNING-SUMMARY.md` +
`SURVIVORS.json` there and into `reports/mutation-nightwatch/LATEST/`. Read
the summary's stack table before scheduling a longer, detached run — a stack
reporting `skipped` (no unique `.sln`, no `stryker-config.json`) or
`skipped_no_parser` needs attention first, not a repeat overnight run that
will report the same gap every time.

## Step 2: Launch detached (survives closing the terminal/session)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/mutation-testing/scripts/mutation_nightwatch.py" --repo-root . --detach
```

`--detach` re-execs the script into a new session/process group (POSIX
`setsid`-equivalent; Windows `DETACHED_PROCESS`) and returns immediately,
printing the child's PID and its `detached-launch.log` path. The run
continues after the launching terminal or Claude Code session closes.

While running, the script holds the OS awake for the run's duration:
`caffeinate -dims` on macOS, `systemd-inhibit --what=sleep:idle` on Linux,
`SetThreadExecutionState` directly on Windows. When none of those are
available, the run still proceeds — but `MORNING-SUMMARY.md`'s Notes section
always carries an explicit `NOTE: sleep inhibition unavailable on <platform>`
line rather than silently risking a sleep-interrupted run. Treat that NOTE as
actionable: install the missing tool, or accept the machine may sleep
mid-run.

## Step 3: Schedule a recurring run (optional)

Per-OS recipes — Task Scheduler, launchd, and cron — live in
[`references/scheduling.md`](references/scheduling.md). Confirm the cadence
and scope with the user before writing any of these (see Constraints above);
they run unattended, indefinitely, until removed.

## Step 4: Morning hand-off

Read `reports/mutation-nightwatch/LATEST/MORNING-SUMMARY.md` first — it
carries per-stack status, the honest score, and any Notes (sleep inhibition,
mechanical-repair failures) from the most recent run, regardless of that
run's timestamped folder name. Both files are refreshed after every module
completes, not only when the run finishes cleanly — a mid-run kill or
timeout still leaves whatever finished so far, never nothing. `SURVIVORS.json` alongside it is the
machine-readable list (`{stack, module, file, line, mutator, change,
status}` per survivor) — hand it to the `mutation-kill` agent (or triage it
per [`mutation-testing/SKILL.md`](../mutation-testing/SKILL.md) Step 4)
rather than re-running the scan to rediscover the same survivors.

A stack reporting `error` in the summary table did not produce a report at
all this run (tool missing, timed out, or crashed before writing its native
report) — its prior night's `SURVIVORS.json` entries (if any) are stale, not
confirmed-fixed; re-run that stack before trusting a "clean" reading.

**Exclude-policy proposal, if present.** When the summary's Notes mention no
committed `mutation-exclude-policy.json` was found, review
`reports/mutation-nightwatch/LATEST/EXCLUDE-POLICY-PROPOSAL.json` — its
`always` entries carry a filename-convention hint (DI wiring, middleware,
generated code), its `propose_and_ask` entries are signal-only and need a
human look. Approve what you agree with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/mutation-testing/scripts/mutation_exclude_policy.py" --approve reports/mutation-nightwatch/LATEST/EXCLUDE-POLICY-PROPOSAL.json --repo-root .
```

This is the only code path that writes the committed policy file — the
night-watch run itself only ever drafts a proposal, never approves one.

## When not to apply

- No mutation tool is set up yet for any stack → run
  [`mutation-testing`](../mutation-testing/SKILL.md) interactively first to
  get one configured and smoke-gated; night-watch only measures, it does not
  install or configure a tool.
- The repo is small enough that a mutation run finishes in a few minutes →
  just run `mutation-testing` directly; detach/sleep-inhibition/scheduling
  are overhead a short run doesn't need.
- Java (pitest) or Go (go-mutesting) is the *only* detected stack → night-
  watch will report `skipped_no_parser`/never invoke the tool; use
  `mutation-testing` directly for those ecosystems today.
