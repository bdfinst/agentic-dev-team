---
name: triage
description: >-
  Investigate a bug, find its root cause, and write a portable triage record to
  DEV_TEAM_REPORTS/triage/<slug>.md with a TDD fix plan. Use when the user
  reports a bug and wants it triaged, says "triage this", "investigate and
  write it up", or wants a hands-off bug investigation that produces an
  actionable record.
argument-hint: "<bug description or error message>"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write, Agent
---

# Bug Triage

Role: worker.

Investigate a bug hands-off, find root cause, and write a TDD fix plan to a
portable triage record at `DEV_TEAM_REPORTS/triage/<slug>.md` — no
issue-tracker dependency.

## Worker constraints

1. Investigate and record; do not fix the bug.
2. Find root cause before recording; do not record on symptoms alone — and do
   not record an unverified, unrelated finding as if it were the root cause;
   use the `unconfirmed` outcome instead.
3. **Be concise.** The record is structured; chat is the `triage-record:` line
   plus a one-line root-cause summary — not the full body.

## Process

### 1. Capture the Problem

Get the bug description from the arguments or conversation. If no description is
given, ask EXACTLY one question: `What's the problem you're seeing?` and stop.
If a description is given, ask nothing — start investigating immediately.

**Scoped exception:** if the description signals a cross-service or
intermittent symptom (it names multiple repos/services, or uses language like
"intermittent", "sometimes", or "inconsistently"), ask ONE additional targeted
question before investigating: `Do you have any of the following: logs, a
sample request/response pair, trace/audit IDs, or a config/pipeline export?`
This is a narrow exception for that signal only — the "ask nothing" rule above
still applies to every other description, and the no-description fallback
question above is unchanged.

Arguments: $ARGUMENTS

### 2. Investigate

Apply the systematic debugging protocol from `skills/systematic-debugging/SKILL.md`:

1. **Reproduce**: Run the failing test or trigger the error
2. **Investigate**: Trace data flow, check recent changes, find working reference code
3. **Root cause**: Form and test a hypothesis

Use the Agent tool with `subagent_type: "Explore"` to deeply investigate the codebase:
related source files and dependencies, existing tests (covered vs missing),
recent changes to affected files (`git log`), error handling in the code path,
and similar patterns elsewhere that work correctly.

**Boundary dead-end:** if static tracing (grep/`codegraph_explore`) returns
zero hits for the relevant identifiers across all checked-out repos, name this
explicitly as **"producer not located in scope"** — do not keep searching
until an unrelated bug-shaped pattern turns up nearby. Carry this named
outcome into the Verification Checkpoint (Step 4), which routes it to the
`unconfirmed` outcome.

### 3. Design TDD Fix Plan

Create an ordered list of RED-GREEN cycles, each a vertical slice:

- **RED**: A specific test capturing broken/missing behavior
- **GREEN**: The minimal code change to make that test pass

Tests verify behavior at the public interface, not implementation details.

### 4. Verification Checkpoint

**Hard gate — cannot be skipped implicitly.** Before writing a `confirmed`
record, state in one sentence what concrete evidence (a log line, a
reproduced failure, an observed value in the actual data path) ties the
hypothesized cause to the *reported symptom*. A boundary dead-end from Step 2
("producer not located in scope") counts as inadequate evidence.

If that evidence exists, proceed to Step 5 with `confidence: confirmed`.
If it does not, do not write a confirmed root-cause section — route to the
`unconfirmed` outcome in Step 5 instead. There is no silent pass-through: a
missing or hand-waved evidence statement means `unconfirmed`, not `confirmed`.

### 5. Write the Triage Record

**Resolve the slug** from the bug title/description with this 8-step algorithm:

1. Lowercase.
2. Strip non-ASCII characters.
3. Replace spaces and underscores with hyphens.
4. Strip every character that is not `[a-z0-9-]`.
5. Collapse consecutive hyphens to one.
6. If longer than 60 characters, truncate to 60, then cut back to the last
   hyphen (so no word is split).
7. Strip leading/trailing hyphens.
8. If the result is empty, fall back to `triage-YYYYMMDD` (today's UTC date).

**Resolve collisions:** if `DEV_TEAM_REPORTS/triage/<slug>.md` exists, append
`-2`, `-3`, … up to `-99` until a free name is found. **Never overwrite** an
existing record.

**Write the file:**

```bash
mkdir -p DEV_TEAM_REPORTS/triage/
```

If `DEV_TEAM_REPORTS/triage/` cannot be created or written (permission/read-only):
report `Cannot write DEV_TEAM_REPORTS/triage/<slug>.md: <error>`, write the
same content to a temp file (`tmp/triage-<slug>.md` or `$TMPDIR`), and print
the full record content to chat so nothing is lost.

The record is YAML frontmatter followed by four sections. Three outcomes are
possible, and they are mutually distinct — not variants of one another:

- **`confirmed`** — the Verification Checkpoint (Step 4) found concrete
  evidence tying the cause to the reported symptom. Full Root Cause Analysis
  and TDD Fix Plan, no banner.
- **`unconfirmed`** — a contributing factor was identified, but the
  checkpoint found no evidence linking it to the reported symptom (including
  a Step 2 boundary dead-end). Banner required; fix plan reframed as
  addressing the contributing factor, not the confirmed cause.
- **not determined** — no plausible cause was found at all. `## TDD Fix Plan`
  is replaced with the fixed string below; there is no `confidence` field
  distinction because there is nothing to mark as confirmed or unconfirmed.

```markdown
---
id: <resolved-slug>
created: <YYYY-MM-DDThh:mm:ssZ>
status: open
confidence: confirmed
---

# <concise bug title>

## Problem

- **Actual behavior**: [what happens]
- **Expected behavior**: [what should happen]
- **Reproduction**: [how to trigger it]

## Root Cause Analysis

[What code path is involved, why it fails, contributing factors. Describe
modules and behaviors, not file paths — the record should survive refactors.]

## TDD Fix Plan

1. **RED**: Write a test that [expected behavior]
   **GREEN**: [Minimal change to pass]

2. **RED**: Write a test that [next behavior]
   **GREEN**: [Minimal change to pass]

**REFACTOR**: [Any cleanup after all tests pass]

## Acceptance Criteria

- [ ] Root cause is addressed (not just symptom)
- [ ] All new tests pass
- [ ] Existing tests still pass
- [ ] No regressions introduced
```

**`confidence` field:** omitted/absent defaults to `confirmed` — no migration
needed for historical triage records predating this schema. Set
`confidence: unconfirmed`
when the Verification Checkpoint routed here without evidence. When
`unconfirmed`, `## Root Cause Analysis` must open with:

```
> **UNCONFIRMED** — contributing factor identified; not verified against the reported symptom.
```

and `## TDD Fix Plan` must explicitly frame the plan as addressing "the
identified contributing factor," not the confirmed root cause.

At least one RED/GREEN cycle is required. **If no root cause was determined,**
the entire `## TDD Fix Plan` body is exactly:

```
Root cause not determined — manual investigation required
```

### 6. Present Results

Print exactly two lines:

1. `triage-record: DEV_TEAM_REPORTS/triage/<resolved-slug>.md` (the actual resolved path)
2. A root-cause summary of at most 120 characters.

Do not repeat the full record body in chat.
