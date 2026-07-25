---
name: feedback-learning
description: Capture amend/learn/remember/forget keywords from the user and update agent or skill configurations. Invoke immediately when the user issues any of these trigger words — parse the change, preview a diff, apply it, and log it to the audit trail.
role: orchestrator
user-invocable: true
---

# Feedback & Learning

Procedure for capturing user feedback, updating configurations dynamically, and maintaining an audit trail of all changes.

## Trigger Keywords

| Keyword | Intent | Example |
| --- | --- | --- |
| **amend** | Modify existing behavior | `amend: the software engineer should prefer functional patterns` |
| **learn** | Teach something new | `learn: our API uses kebab-case URLs` |
| **remember** | Persist a preference across sessions | `remember: always run tests before completing tasks` |
| **forget** | Remove a previous preference | `forget: the kebab-case URL convention` |

All four follow the same processing flow. The distinction is semantic (helping the user express intent), not mechanical.

## Where Changes Are Written

The plugin ships as a read-only cache — agent and skill files inside the plugin cannot be edited. Instead, feedback is persisted to **project-local files** that the user controls and that Claude Code loads automatically.

### Resolution order

When processing a feedback keyword, determine the right destination:

| Change type | Write to | Why |
| --- | --- | --- |
| Project convention or preference | **Project `CLAUDE.md`** (`.claude/CLAUDE.md` or repo-root `CLAUDE.md`) | Loaded every session, applies to all agents |
| Review context (domain knowledge, known issues, team norms) | **`REVIEW-CONTEXT.md`** in project root | Read by `/code-review` and passed to every review agent |
| Agent behavior override for this project | **Project `CLAUDE.md`** under a `## Agent Overrides` section | Overrides plugin defaults without editing plugin files |
| Cross-session memory (decisions, project state) | **`.claude/memory/`** files | Persists across context resets |
| Rollback a previous change | Reverse the edit in whichever file it was written to | Logged as `type: "rollback"` |

### What NOT to do

- Do not edit files inside the plugin cache (`~/.claude/plugins/cache/...`). Changes there are overwritten on plugin updates.
- Do not create new agent or skill files in the project. Instead, add override instructions to project `CLAUDE.md`.

### Project CLAUDE.md structure for overrides

When writing agent behavior overrides, add them under a dedicated section so they're easy to find and manage:

```markdown
## Agent Overrides

### Software Engineer
- Prefer functional programming patterns over OOP
- Always use `const` over `let` in JavaScript

### Architect
- Default to event-driven architecture for new services
```

These instructions are loaded into every session and take precedence over the plugin's built-in agent definitions because project `CLAUDE.md` is processed after plugin files.

## Processing Flow

1. **Parse**: Identify the trigger keyword and extract the change request
2. **Classify**: Determine change type using the resolution table above
3. **Preview**: Show the user the proposed edit as a diff before applying
4. **Apply**: Write the change to the target file
5. **Evaluate**: Eval-gate the change if it touches a fixtured review agent (see below)
6. **Log**: Record the change in the audit trail
7. **Verify**: Read back the modified section to confirm correctness

### Approval rules

- Preference and convention changes: apply after diff preview
- New sections or structural edits to CLAUDE.md: require explicit approval
- Rollbacks: apply after confirming which change to reverse

## Evaluate — the eval gate (#860)

A change that mutates a review agent's effective behavior — a direct edit to
`plugins/dev-team/agents/*.md` (when developing this repo) or a project-side
`CLAUDE.md > Agent Overrides > <agent>` / `REVIEW-CONTEXT.md` entry — is a
harness edit, not a preference tweak. The paper this closes a gap against
(*Code as Agent Harness*, §3.5.2–3.5.3) warns that a self-improving loop
optimizing against "the diff looked reasonable" is optimizing against a weak
verifier and can learn the wrong thing. `/agent-eval --agent <name>` is the
falsifier; this step wires it into the mutation path.

This gate sits between **Apply** and **Log**. It never blocks the edit
itself — the file is already written by the time this step runs. What it
gates is **adoption**: whether the changelog entry for this change can reach
`adoption_status: "adopted"`.

### 1. Determine whether the change is gated

Scan `evals/expected/*.json` for `applicableAgents` arrays. If the changed
agent's name (the `component` field — see Audit Trail below) appears in any
of them, the change is **gated**. Two graceful-degradation cases, neither of
which blocks:

- **No `evals/` directory at all** (the normal cache-only plugin-install
  case — most users have the plugin as a read-only cache with no `evals/`
  shipped). Write `eval_verdict: "not-applicable"` and tell the operator:
  "This install has no `evals/` directory — eval-gating requires the plugin
  repo. Run `/agent-eval --agent <name>` from a clone of
  `bdfinst/agentic-dev-team` if you want a falsifier for this change."
- **`evals/` exists but the agent has no fixtures.** Write
  `eval_verdict: "not-applicable"` and name the fixture gap in both the
  changelog entry and the chat reply (never silent — this is the
  documented fallback, not an error).

If ungated (the change doesn't touch a review agent, or touches one with no
fixtures), skip straight to **Log** with `adoption_status: "adopted"` (or
`not-applicable`'s equivalent — see schema below) — no eval run, no cost.

### 2. Get the pre-score

Read `evals/baseline.json`, filtered to pairs whose agent is the touched
one. If baseline entries exist for this agent, that is `eval_pre` —
`{"passed": <n>, "total": <n>, "source": "baseline"}` — no live run, no
cost. Only when the agent has **zero** baseline entries, dispatch a fresh
`/agent-eval --agent <name>` first to establish `eval_pre` (`source` becomes
the resulting transcript path instead of `"baseline"`).

### 3. Pause for approval, then dispatch the targeted eval

Before dispatching *any* live `/agent-eval` run (pre-run or post-run), show
the operator the cost estimate and wait for approval — consistent with the
opt-in live-eval posture (#134). Once approved, dispatch:

```
/agent-eval --agent <name>
```

Always targeted, always cache-on. **Never** dispatch the full unfiltered
`/agent-eval` suite from this gate — that is a distinct, much more expensive
operation the operator runs deliberately, not something a single config
mutation should trigger.

Write the changelog entry with `adoption_status: "pending-eval"` *before*
this run starts (see schema below), then finalize it once the run completes.

### 4. Compare and decide adoption

| `eval_post` vs `eval_pre` | `eval_verdict` | Default `adoption_status` |
| --- | --- | --- |
| Post ≥ pre, no new pair regresses | `improved` or `unchanged` | `adopted` |
| Post < pre (any pair that was passing now fails) | `regressed` | `rejected` or `rolled-back` |

**Regression is always a human decision, never an automatic rollback.** The
default proposal to the human is `rejected`/`rolled-back`; the human may
instead choose `overridden`, which requires a non-empty
`override_rationale` (who decided, and why the regression is acceptable).
Auto-rollback never fires without that logged human choice — this matches
the plugin's Human-in-the-Loop principle and `/harness-audit`'s
"do not auto-edit" posture.

## Audit Trail

All changes are logged in `.claude/metrics/config-changelog.jsonl` (one JSON object per line, append-only).

```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "type": "amend",
  "trigger": "user",
  "description": "Updated software engineer to prefer functional patterns",
  "file_modified": "CLAUDE.md",
  "section_modified": "Agent Overrides > Software Engineer",
  "previous_value": "",
  "new_value": "- Prefer functional programming patterns over OOP",
  "approved_by": "user",
  "evidence": {
    "metrics": ["rework"],
    "direction": "decrease",
    "window_sessions": 10
  }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `timestamp` | Yes | ISO 8601 |
| `type` | Yes | `amend`, `learn`, `remember`, `forget`, `rollback`, `validation` |
| `trigger` | Yes | `user` or `system` (learning loop) |
| `description` | Yes | Human-readable summary |
| `file_modified` | Yes | Path of the file changed |
| `section_modified` | Yes | Which section within the file |
| `previous_value` | Yes | Content before (empty string if new) |
| `new_value` | Yes | Content after (empty string if removed) |
| `approved_by` | Yes | `user` or `auto` |
| `evidence` | Yes on `amend`/`learn`/`remember` entries (#866) | Either a structured object or the literal string `"unmeasurable"` — see below. Never silently absent. |

### The `evidence` field (validated-outcome weighting, #866)

Every new `amend`/`learn`/`remember` entry names how its own effect can be
checked, so `/harness-audit` can later close the loop instead of letting
lessons accumulate on the strength of the approval that admitted them alone.

**Structured case** — the lesson is expected to move a metric in
`metrics/session-digest.jsonl`:

```json
"evidence": {
  "metrics": ["rework"],
  "direction": "decrease",
  "window_sessions": 10
}
```

- `metrics`: one or more metric names resolvable in a `session-digest.jsonl`
  record (e.g. `rework`, `accuracy`, `cost_usd`, or a dotted path such as
  `rework.failed_edits`).
- `direction`: `"increase"` or `"decrease"` — which way the metric should move
  if the lesson helped.
- `window_sessions`: integer N — how many digest records after adoption to
  observe before judging. **Default: 10** (mirrors `/harness-audit`'s existing
  "minimum 10 logged review runs" floor).

**Unmeasurable case** — when no digest metric can plausibly reflect the
lesson's effect (most prose `.claude/memory/` notes land here), write the literal
string instead of an object:

```json
"evidence": "unmeasurable"
```

**Default when the author names no metric**: `evidence: rework` with
`direction: "decrease"` and `window_sessions: 10` — most lessons aim to
reduce rework, so this is the default rather than refusing to log the
lesson. Authors can still explicitly set a different metric, direction, or
`"unmeasurable"`.

**Prose lessons (`.claude/memory/` notes) are in scope.** The `evidence` field
attaches at this changelog layer regardless of which resolution-order
destination the lesson was written to; a memory-note lesson typically carries
`"unmeasurable"`. Anything not logged to `.claude/metrics/config-changelog.jsonl`
is out of scope by construction.

**Legacy entries** (written before this field existed) have no `evidence`
key at all. `/harness-audit` surfaces them as a count — it never assigns
them a verdict or proposes a rollback on evidence grounds.

### Validation verdicts and rollback proposals (#866)

`/harness-audit` reads this changelog and appends new `type: "validation"`
entries recording a verdict (`validated` / `neutral` / `harmful` / `insufficient
data`) for every matured, structured-evidence lesson — see
[harness-audit](../harness-audit/SKILL.md) → Lesson Validation. These
verdict entries are **new appended lines**, never edits to the original
entry; the changelog stays append-only.

A `harmful` verdict produces a **rollback proposal** in the harness-audit
report (never an automatic rollback). To action one:

1. Locate the original entry by the proposal's `references_timestamp`.
2. Follow the existing [Rollback](#rollback) procedure below using that
   entry's `file_modified` / `section_modified` / `previous_value`.
3. Log the rollback as usual — a new `type: "rollback"` entry.

A human always decides whether to apply a harmful-verdict rollback; the
validation pass only ever proposes.

### Change-contract schema extension (#860)

The nine fields below are **required only for entries that gate through
Evaluate above** — i.e. `component` names a review agent that has eval
fixtures. Older entries and entries for ungated changes remain valid as-is;
this is a backward-compatible, append-only extension, never a retroactive
rewrite of prior lines. A reference validator lives at
`plugins/dev-team/hooks/lib/config_changelog_schema.py`
(`validate_entry(entry, fixtured_agents)`).

| Field | Required (gated only) | Type | Meaning |
| --- | --- | --- | --- |
| `component` | Yes | string | Artifact whose behavior changes (e.g. `agents/security-review.md` or `CLAUDE.md > Agent Overrides > security-review`) |
| `failure_mode_targeted` | Yes | string | The observed failure the change intends to fix |
| `predicted_improvement` | Yes | string | Falsifiable prediction (e.g. "sec-xss-vulnerable stops flapping; no other pair regresses") |
| `eval_pre` | Yes | object | `{passed, total, source}` — `source` is `"baseline"` (`evals/baseline.json`) or a transcript path |
| `eval_post` | Yes | object | `{passed, total, transcript}` — transcript under `.claude/evals/transcripts/` |
| `eval_verdict` | Yes | string | `improved` \| `unchanged` \| `regressed` \| `not-applicable` (no fixtures) |
| `adoption_status` | Yes | string | `pending-eval` \| `adopted` \| `rejected` \| `rolled-back` \| `overridden` |
| `override_rationale` | Iff `adoption_status: "overridden"` | string | Names the human and the reason the regression was accepted |
| `rollback_pointer` | Yes | string | How to undo: the entry's own `previous_value` + `file_modified`/`section_modified` (existing rollback mechanics), or a git ref for direct agent-file edits |

Example gated entry (written once, after the eval completes — the
`pending-eval` interim state is a separate appended line, not an in-place
mutation):

```json
{
  "timestamp": "2026-07-06T00:00:00Z",
  "type": "amend",
  "trigger": "system",
  "description": "Tightened XSS detection regex",
  "file_modified": "agents/security-review.md",
  "section_modified": "## Detect",
  "previous_value": "old regex",
  "new_value": "new regex",
  "approved_by": "user",
  "component": "agents/security-review.md",
  "failure_mode_targeted": "sec-xss-vulnerable flapping",
  "predicted_improvement": "sec-xss-vulnerable stops flapping; no other pair regresses",
  "eval_pre": { "passed": 20, "total": 21, "source": "baseline" },
  "eval_post": { "passed": 21, "total": 21, "transcript": ".claude/evals/transcripts/x.json" },
  "eval_verdict": "improved",
  "adoption_status": "adopted",
  "rollback_pointer": "previous_value above"
}
```

## Rollback

```
amend: rollback the last change to CLAUDE.md
amend: rollback all changes from today
```

1. Read `.claude/metrics/config-changelog.jsonl` to find the entry — fall back
   to the legacy `metrics/config-changelog.jsonl` if the new path doesn't
   exist (a downstream user's history may still be at the old path):
   `log=".claude/metrics/config-changelog.jsonl"; [ -f "$log" ] || log="metrics/config-changelog.jsonl"`
2. Restore `previous_value` to the target file and section
3. Log the rollback as a new entry with `type: "rollback"`

## Learning Loop

After task completion, the orchestrator captures learnings in two ways:

### Post-task reflection

After completing a feature or fixing a complex bug, review the git diff and any review feedback and ask: "What do I wish I'd known at the start?" Classify each insight:

| Category | Example |
| --- | --- |
| **Gotcha** | "The API returns 200 with an error body" |
| **Pattern** | "Use factory functions for test fixtures" |
| **Anti-pattern** | "Don't mock the database for integration tests" |
| **Decision** | "Chose event sourcing over CRUD for audit trail" |
| **Edge case** | "Empty arrays and null are treated differently by the serializer" |

Only capture non-obvious insights — if it's clear from reading the code, skip it. Present proposals to the user; persist approved ones using the resolution table above. Log with `trigger: "system"`.

### Recurring correction detection

The orchestrator also watches for patterns across tasks:

| Signal | Possible action |
| --- | --- |
| 3+ user corrections on same topic | Propose a project CLAUDE.md update |
| Agent consistently defers to another | Propose collaboration protocol tweak |
| Skill results repeatedly rejected | Propose skill guideline override |
| Context summarization triggered frequently | Propose loading profile adjustment |

When a pattern is detected (minimum 3 occurrences), propose the change with rationale. User approves or rejects. If approved, apply and log with `trigger: "system"`.

## Pending-Review Queue Disposition

When `/session-review` surfaces entries from `.claude/metrics/pending-review.jsonl`, this
skill handles the approve or reject decision for each finding.

### Matching

Identify the queue entry by `source` + `queued_at` combination (handles duplicate-
content entries safely).

### Approval path

1. Apply the proposed change (following the standard Processing Flow above).
2. Append to `.claude/metrics/config-changelog.jsonl` as usual.
3. Write `reviewed_at` (ISO-8601 UTC) and `approved_by` (the user identifier from
   `approved_by` in the existing audit schema) back into the matching entry in
   `.claude/metrics/pending-review.jsonl`.

### Rejection path

1. Do **not** apply the proposed change.
2. Do **not** write to `.claude/metrics/config-changelog.jsonl`.
3. Write `rejected_at` (ISO-8601 UTC) and `rejected_by` (same format as
   `approved_by`) into the matching entry in `.claude/metrics/pending-review.jsonl`.

### Queue entry schema (reference)

```json
{
  "queued_at":   "2026-06-01T12:00:00Z",
  "source":      "session-learning-trigger",
  "session_id":  "abc-123",
  "findings": [
    {
      "lever":           "instruction-rule",
      "evidence":        "3 occurrences in last 5 sessions",
      "target_artifact": "agents/orchestrator.md",
      "proposed_change": "Add constraint",
      "route":           "feedback-learning"
    }
  ],
  "reviewed_at": "2026-06-02T09:00:00Z",
  "approved_by": "user",
  "rejected_at": "2026-06-02T09:00:00Z",
  "rejected_by": "user"
}
```

`reviewed_at` and `approved_by` are added on approval; `rejected_at` and
`rejected_by` are added on rejection. A finding gains exactly one disposition.

## Constraints

- Never edit plugin cache files — all changes go to project-local files
- Never auto-apply without user preview for structural modifications
- Behavioral tweaks (tone, preferences) can be auto-applied; structural changes (new sections, removed overrides) require approval
- The changelog is append-only — never delete entries
- Every new `amend`/`learn`/`remember` entry carries an `evidence` field — a structured object or `"unmeasurable"`, never silently absent (#866)
- A `harmful` validation verdict from `/harness-audit` is a rollback *proposal* only — never auto-apply it without user confirmation
