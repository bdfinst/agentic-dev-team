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
  Read, Write, Glob, Grep,
  Bash(python3 *), Bash(gh *), Bash(command -v gh),
  Skill(ship *), Skill(cost-report *),
  mcp__github__search_issues, mcp__github__issue_read,
  mcp__github__search_pull_requests, mcp__github__issue_write,
  mcp__github__add_issue_comment
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

## gh CLI availability (#1700)

Check once, before Step 1: `command -v gh`.

- **gh present** (the normal case — a local/CI session with the CLI
  installed and authenticated): every step below runs exactly as written,
  invoking `gh` directly (via `autoship_reclaim.py`/`autoship_group.py`'s
  live fetch, and the raw `gh issue edit`/`gh issue comment` calls in Steps
  3b/3d).
- **gh absent** (a Claude Code web/cloud session — GitHub access there is
  provided only through the `mcp__github__*` tools, never a `gh` binary):
  every step below that would otherwise shell out to `gh` instead uses the
  MCP-tool path called out in that step. The scripts themselves never gain a
  network code path of their own — they stay pure decision logic over
  `--input-file` JSON (already true for `autoship_discover.py`'s read side
  and, since #1700, `autoship_reclaim.py`'s write side too via
  `--emit-actions-only`); only the data gathering and the actual GitHub
  mutation move up to this skill, because MCP tools are only callable from
  the agent context, never from inside a Python subprocess.
  - **Known gap, gh-absent discovery only**: `autoship_group.py` (via the
    shared `autoship_state.fetch_eligible_issues` eligibility filter it
    calls into) needs two GraphQL-shaped fields (`subIssuesSummary`,
    `closedByPullRequestsReferences`) that `gh issue list --json` computes
    for free but that the REST-backed MCP tools don't return in one call.
    The MCP-path instructions in Step 2 approximate them —
    `mcp__github__issue_read` (method `get`) per candidate for the epic
    check, and a `mcp__github__search_pull_requests` query for the
    open-linked-PR check — and are deliberately conservative (treat an
    ambiguous match as "has an open PR", i.e. skip it) since a false include
    is worse than a false exclude for an autoship gate. This is real but
    bounded: it only touches the small number of issues that already carry
    the ready label, not the whole repo. Step 2 also documents a second,
    narrower gh-absent gap specific to grouping itself — the
    `blockedBy`/`blocking`/`parent` fields `autoship_group.py`'s dependency
    and shared-parent signals need, which this skill's MCP toolset has no
    call for at all.
  - `/ship` (Step 3c) has its own separate `gh` dependency (`Bash(gh pr *)`,
    `Bash(gh issue *)` in its own `allowed-tools`) that this fix does not
    touch — a gh-absent round can reclaim/discover/label via MCP, but `/ship`
    itself still needs `gh` to open the PR. Out of scope for #1700; file a
    follow-up if full gh-less autoship end-to-end is wanted.

## Step 1 — Reclaim orphaned issues

Run the reclaim script to relabel any stale `autoship:in-progress` issues back
to `autoship:blocked` before discovery, so they are not counted against
`--max-issues` and are instead queued for human triage.

**gh present:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_reclaim.py" \
  [--dry-run]           # pass when --dry-run was given
```

**gh absent:**

1. Fetch open issues labeled `autoship:in-progress` via
   `mcp__github__search_issues` (`query: "is:issue is:open label:autoship:in-progress"`,
   `fields: ["number", "title", "labels", "updated_at"]`).
2. Build a JSON array matching `autoship_reclaim.py`'s `--input-file` schema
   — one object per issue with `number`, `title`, `state: "OPEN"`, `labels`
   (as `[{"name": "..."}, ...]`), and `labeled_at` (use `updated_at` from the
   search result — the script's own live-fetch path falls back to
   `updatedAt` the same way when it can't resolve the real timeline event, so
   this is not a regression). Write it to a scratch file.
3. Run the script against that file, with `--emit-actions-only` (never
   `--dry-run` and `--emit-actions-only` together unless `--dry-run` was
   itself given — dry-run alone already previews correctly with no gh calls):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_reclaim.py" \
     --input-file <scratch-file> --emit-actions-only \
     [--dry-run]           # pass when --dry-run was given
   ```

4. In `--dry-run` mode, the script's `would-reclaim` preview lines are the
   report — stop here, nothing to execute. Otherwise, the script prints one
   JSON action per line (`{"number", "comment", "relabel_from",
   "relabel_to"}`, exit 0) or, on a failure it detects itself (e.g. a
   malformed input file), a `autoship_reclaim: ...` error on stderr with a
   non-zero exit — treat that the same as today's "reclaim failure is
   non-fatal" handling below. For each successfully-emitted action, execute
   it directly: `mcp__github__add_issue_comment` with the action's `comment`,
   then `mcp__github__issue_write` (method `update`, removing
   `relabel_from` and adding `relabel_to` via the `labels` field — read the
   issue's current labels first, since `issue_write`'s `labels` replaces the
   full set rather than diffing it).

Report how many issues were reclaimed (or would be reclaimed in dry-run). A
reclaim failure is non-fatal — log the error and continue to discovery.

## Step 2 — Discover eligible issues

Run the two-stage grouping/queueing pipeline to select and order the issues
this round will process:

**gh present:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_group.py" \
  [--label <label>] \
  | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_queue.py" \
  --max-issues <N>
```

`autoship_group.py` self-fetches the **full** eligible pool — it takes no
`--max-issues` truncation at that layer, because grouping needs full
visibility across every eligible issue to find dependency, shared-parent,
and shared-label signals before anything is capped. It groups that pool into
batches and ungrouped singles via those deterministic signals.

**gh absent** — `autoship_group.py` already supports `--input-file` to
bypass `gh` entirely on the read side (no script change needed); this skill
supplies that file via MCP tools instead, the same way this step's `gh
absent` path worked before this pipeline replaced `autoship_discover.py`:

1. Fetch open issues labeled `autoship:ready` (or `--label`) via
   `mcp__github__search_issues` (`query: "is:issue is:open label:<label>"`,
   `fields: ["number", "title", "labels", "created_at"]`).
2. For each candidate, resolve the two fields `gh issue list --json` computes
   for free but the search result doesn't carry (see the "Known gap" note
   above):
   - **Epic check**: `mcp__github__issue_read` (method `get`, that issue
     number) — use its `sub_issues_summary.total` (or `has_children`) as
     `subIssuesSummary.total`.
   - **Open-linked-PR check**: `mcp__github__search_pull_requests`
     (`query: "is:pr is:open <number> in:body repo:<owner>/<repo>"`). Any
     result found → treat as an open linked PR (conservative: this is an
     approximation of GitHub's own closing-keyword graph, not an exact
     match — a false "has an open PR" only costs deferring the issue to next
     round, which is safe; a false negative would let a genuinely
     PR-in-flight issue double-dispatch, which is not).
3. **Known gap, gh-absent grouping only**: `autoship_group.py`'s
   native-dependency and shared-parent signals need `blockedBy`, `blocking`,
   and `parent` — fields this skill's REST-backed MCP toolset (the
   `mcp__github__*` tools listed above) has no call for. A gh-absent round
   cannot resolve them, so leave all three out of the scratch file entirely
   rather than guessing — `autoship_group.py`'s signal functions already
   treat a missing field as "no signal", never an error (they read it via
   `.get(...)`, same as the epic/PR-check gap above). Only the shared-label
   signal (which needs just the `labels` field already fetched in step 1)
   still groups issues in this mode; the round still ships every eligible
   issue, just solo instead of batched wherever a dependency/parent signal
   would otherwise have fired.
4. Build a JSON array matching `autoship_group.py`'s required fields —
   `autoship_state.BASE_REQUIRED_FIELDS` (`number`, `title`, `state:
   "OPEN"`, `createdAt` from `created_at`, `labels`,
   `closedByPullRequestsReferences` as `[{"state": "OPEN"}]` or `[]` per the
   step-2 check, `subIssuesSummary` as `{"total": N}`) — omitting
   `blockedBy`/`blocking`/`parent` per the gap above; they are optional on
   the `--input-file` path, not required. Write it to a scratch file.
5. Run the pipeline's first stage with `--input-file <scratch-file>`; the
   second stage (`autoship_queue.py`) never touches `gh` and needs no
   `gh absent` variant of its own:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_group.py" \
     --input-file <scratch-file> \
     [--label <label>] \
     | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autoship_queue.py" \
     --max-issues <N>
   ```

Its output is piped directly into `autoship_queue.py`, which applies this
round's real `--max-issues` cap and produces the ordered dispatch queue:
`{"queue": [...], "deferred": [...]}`. Batches dispatch **whole** or are
deferred **whole** — a batch is never split across `queue` and `deferred`.

`autoship_discover.py` is **not** part of this pipeline anymore. Its own CLI
remains available unchanged for any other caller — do not modify or remove
that script.

The `queue` array is what the per-issue loop (Step 3) will process — one
entry per dispatch unit, each either `{"type": "batch", "batch_id": ...,
"issues": [...]}` or `{"type": "solo", "issue": N}`. **Step 3's prose below is
still written for the old `{number, title}` shape** — it has not yet been
updated to consume this new queue shape. That update is a later, separate
change; do not treat Step 3 as already handling batch/solo units.

If the queue is empty (both `queue` and `deferred` empty), print "No eligible
issues found this round." and stop (record an empty round in the log before
exiting).

In `--dry-run` mode, print the discovered queue and stop here without
proceeding to per-issue processing.

The `--label` flag, when given, now flows to `autoship_group.py --label
<label>` instead of `autoship_discover.py --label <label>`.

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

**gh present:**

```bash
gh issue edit <number> \
  --remove-label autoship:ready \
  --add-label autoship:in-progress
```

**gh absent:** `mcp__github__issue_write` (method `update`, that issue
number) — read the issue's current labels first (`issue_read` method `get`),
then pass the full `labels` list with `autoship:ready` removed and
`autoship:in-progress` added (the tool replaces the full label set, it does
not diff against `--remove-label`/`--add-label` semantics).

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

   **gh present:**

   ```bash
   gh issue edit <number> \
     --remove-label autoship:in-progress \
     --add-label autoship:blocked
   ```

   **gh absent:** `mcp__github__issue_write` (method `update`), same
   read-current-labels-first pattern as Step 3b.
3. Post a comment on the issue with the blocking question(s):

   **gh present:**

   ```bash
   gh issue comment <number> \
     --body "autoship blocked: requires stakeholder input\n\n<questions>"
   ```

   **gh absent:** `mcp__github__add_issue_comment` with the same body.
4. Record outcome `"blocked"` with `blocked_reason: "<questions>"` for this
   issue.
5. **Continue to the next issue.** A blocked issue does not halt the round.

### 3e — Classify outcome

After a non-blocked `/ship` completes, record the start ISO timestamp that was
captured just before invoking `/ship` in Step 3c, then run the classifier:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/classify_ship_outcome.py" \
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
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py" record \
  --round-id "<round_id>" \
  --attempted "<short note: what was attempted>" \
  --outcome "<short note: shipped|failed|blocked|unrecognized>" \
  --next-action "<short note: next issue or stop>" \
  --session "$CLAUDE_SESSION_ID"

python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/iteration_journal_gate.py" check \
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
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/autoship_log.py" \
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
