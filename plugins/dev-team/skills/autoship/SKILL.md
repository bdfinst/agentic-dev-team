---
name: autoship
description: >-
  Orchestrate a bounded round of automated issue processing: reclaim orphaned
  in-progress issues, discover eligible `autoship:ready` issues, and invoke
  `/ship` sequentially for each — stopping at cost or count caps and surfacing
  blocked items without halting the round. Requires `--max-issues` and
  `--max-cost-usd`. Use when you want a self-contained automated delivery
  round driven from the issue tracker.
argument-hint: "--max-issues N --max-cost-usd N [--dry-run] [--label LABEL]"
user-invocable: true
effort: medium
allowed-tools: >-
  Read, Glob, Grep,
  Bash(python3 *), Bash(gh *),
  Skill(ship *), Skill(cost-report *)
---

# Autoship

Role: orchestrator. This skill runs one bounded round of automated issue
dispatch. It does not implement code, review, or merge — it sequences the
existing `/ship` pipeline per issue and logs each outcome.

You have been invoked with the `/autoship` command.

## Orchestrator constraints

1. **Never start without both caps.** Refuse immediately if `--max-issues` or
   `--max-cost-usd` is missing from `$ARGUMENTS`.
2. **Sequential only.** Process one issue at a time. Do not launch concurrent
   `/ship` invocations.
3. **Delegate every phase.** Call the owning scripts and skills; do not
   re-implement discovery, reclaim, shipping, or cost reading here.
4. **No scheduling logic.** This skill runs once per invocation. Timer or
   recurring execution is the caller's responsibility.
5. **Dry-run is preview only.** When `--dry-run` is given, run reclaim and
   discovery in preview mode; never label, comment, invoke `/ship`, or write
   to the round log.

## Parse Arguments

Arguments: $ARGUMENTS

Required:
- `--max-issues N` — maximum number of issues to process this round (positive
  integer).
- `--max-cost-usd N` — budget ceiling in USD for the entire round (positive
  number).

Optional:
- `--dry-run` — preview mode: report what would run without side effects.
- `--label LABEL` — override the eligibility label (default: `autoship:ready`).

If either required argument is absent, print this message and stop:

```
autoship: --max-issues and --max-cost-usd are both required.
Usage: /autoship --max-issues N --max-cost-usd N [--dry-run] [--label LABEL]
```

## Step 1 — Reclaim orphaned issues

Run the reclaim script to relabel any stale `autoship:in-progress` issues back
to `autoship:blocked` before discovery, so they are not counted against
`--max-issues` and are instead queued for human triage.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/autoship_reclaim.py \
  [--dry-run]           # pass when --dry-run was given
```

Report how many issues were reclaimed (or would be reclaimed in dry-run). A
reclaim failure is non-fatal — log the error and continue to discovery.

## Step 2 — Discover eligible issues

Run the discovery script to select the issues this round will process.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/autoship_discover.py \
  --max-issues <N> \
  --max-cost-usd <max_cost_usd> \
  [--label <label>]     # pass when --label was given
```

The script prints a JSON array of `{number, title}` objects, oldest-first,
capped at `--max-issues`. Parse it.

If the array is empty, print "No eligible issues found this round." and stop
(record an empty round in the log before exiting).

In `--dry-run` mode, print the discovered list and stop here without proceeding
to per-issue processing.

## Step 3 — Per-issue processing loop

Process each discovered issue **strictly in order** (no concurrency).

For each issue `{number, title}`:

### 3a — Cost cap check

Before starting an issue, read the current round cost:

```bash
# Invoke /cost-report to get the total cost incurred since round start
```

If the accumulated cost so far meets or exceeds `--max-cost-usd`, stop the
loop with the message:

```
autoship: cost cap reached (${accumulated:.2f} >= ${max_cost_usd:.2f}).
Stopping before issue #<number>.
```

Record the round summary with `status: "cost_cap_reached"` for the remaining
issues.

### 3b — Label issue in-progress

```bash
gh issue edit <number> \
  --remove-label autoship:ready \
  --add-label autoship:in-progress
```

### 3c — Invoke /ship

Invoke `/ship` with:
- The issue title/number as the feature description
- `--no-auto-merge` (always — the round does not auto-merge PRs)
- `DEV_TEAM_AUTO_APPROVE=1` in the environment so the pipeline does not pause
  at human-confirmation prompts

```
/ship "Issue #<number>: <title>" --no-auto-merge
```

Ensure every PR body created by this `/ship` invocation includes `Closes #<number>`.
Pass the issue number to `/ship` so it can include the closing reference when
calling `/pr`.

Capture the full output of `/ship` as `ship_output`.

### 3d — Detect stakeholder-input blocker

Scan `ship_output` for the pattern `requires-stakeholder-input` (case-insensitive).
If found:

1. Extract the blocking question(s) from the output (the text immediately
   following the `requires-stakeholder-input` marker).
2. Label the issue:
   ```bash
   gh issue edit <number> \
     --remove-label autoship:in-progress \
     --add-label autoship:blocked
   ```
3. Post a comment on the issue with the blocking question(s):
   ```bash
   gh issue comment <number> \
     --body "autoship blocked: requires stakeholder input\n\n<questions>"
   ```
4. Record outcome `"blocked"` with `blocked_reason: "<questions>"` for this
   issue.
5. **Continue to the next issue.** A blocked issue does not halt the round.

### 3e — Classify outcome

After a non-blocked `/ship` completes, record the start ISO timestamp that was
captured just before invoking `/ship` in Step 3c, then run the classifier:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/classify_ship_outcome.py \
  --review-value .claude/metrics/review-value.jsonl \
  --verify-log   metrics/verify-log.jsonl \
  --since        <start_iso>
```

The classifier prints one of: `success`, `convergence_failure`, `unrecognized`.

Map to a display status word:
- `success` → `"shipped"`
- `convergence_failure` → `"failed"`
- `unrecognized` → `"unrecognized"`

### 3e.1 — Hard-block: iteration journal gate (#1168)

Before advancing to the next issue, append a structured decision entry for
this issue and confirm the gate allows advancement — this is a hard block,
not the advisory `progress-guardian` gate:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py record \
  --round-id "<round_id>" \
  --attempted "<short note: what was attempted>" \
  --outcome "<short note: shipped|failed|blocked|unrecognized>" \
  --next-action "<short note: next issue or stop>" \
  --session "$CLAUDE_SESSION_ID"

python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py check \
  --round-id "<round_id>" \
  --session "$CLAUDE_SESSION_ID"
```

If `check` exits non-zero, do not advance to the next issue — the `record`
call above must have failed to land; retry it before continuing. A
successful `record` followed immediately by `check` for the same `round_id`
always allows advancement. Skip both calls in `--dry-run` mode.

### 3f — Append round record

Append one entry per issue to `.claude/metrics/autoship-log.jsonl` using the log
library:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/autoship_log.py \
  --log-path .claude/metrics/autoship-log.jsonl \
  --json '{"round_id":"<round_id>","issue":<number>,"status":"<status>","blocked_reason":"<reason_or_null>"}'
```

`round_id` is an ISO-8601 timestamp generated once at round start (before
Step 1). `blocked_reason` is the extracted question string for blocked issues,
`null` otherwise.

Skip the log write in `--dry-run` mode.

## Step 4 — Round summary

After the loop ends (all issues processed, cost cap reached, or dry-run),
print a round summary to chat:

```
## Autoship round summary

Round ID : <round_id>
Issues   : <processed_count> processed, <total_discovered> discovered
Budget   : $<accumulated:.2f> / $<max_cost_usd:.2f>

| Issue | Title                     | Status       | Notes                    |
|-------|---------------------------|--------------|--------------------------|
| #NNN  | <title (truncated at 40)> | shipped      |                          |
| #NNN  | <title>                   | blocked      | <blocked_reason>         |
| #NNN  | <title>                   | skipped      | cost cap reached         |
```

Status words used in the table and the log:
- `shipped` — `/ship` completed and classifier returned `success`
- `failed` — classifier returned `convergence_failure`
- `unrecognized` — classifier returned `unrecognized`
- `blocked` — `requires-stakeholder-input` detected in `/ship` output
- `skipped` — cost cap reached before this issue started

The round summary is also written to `.claude/metrics/autoship-log.jsonl` as a final
`round_summary` record (not written in dry-run mode):

```json
{
  "round_id": "<round_id>",
  "event": "round_summary",
  "processed": <N>,
  "discovered": <N>,
  "cost_usd": <accumulated>,
  "status": "complete" | "cost_cap_reached" | "dry_run"
}
```

## Notes

- **No scheduling.** There is no timer or interval mechanism in this skill.
  Run `/autoship` manually or wire it to an external scheduler.
- **Human-merge required.** All PRs opened by this round use `--no-auto-merge`.
  A human must review and merge each PR.
- **Blocked issues need human triage.** Issues labeled `autoship:blocked` will
  not be picked up again until a human resolves the question and updates the
  label back to `autoship:ready`.
- **Cost tracking.** The cost check (Step 3a) uses `/cost-report` output.
  The accuracy of the cap depends on the cost-report tool's granularity.
- **Idempotent reclaim.** Running `/autoship` when no stale in-progress issues
  exist is safe — the reclaim step reports "No orphaned issues found" and the
  round proceeds normally.
