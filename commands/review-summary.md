---
name: review-summary
description: >-
  Generate a compact summary of the most recent code review results and
  save it for future sessions. Use this at the end of a coding session after
  /code-review has run, or when the user says "summarize the review", "save
  the results", "generate a summary", or wants to preserve review context
  before closing a session.
argument-hint: "[--from <json-file>]"
user-invocable: true
allowed-tools: Read, Write, Glob, Bash(date *), Bash(git rev-parse *), Bash(git branch *), Bash(mkdir *)
---

# Review Summary

Role: orchestrator. This skill summarizes and persists review results — it does not review code.

You have been invoked with the `/review-summary` skill. Generate a compact summary of the most recent code review.

## Orchestrator constraints

1. **Do not re-analyze code.** Summarize existing review results only.
2. **Keep summaries under 150 words.** Compact summaries replace
   full conversation history for future sessions (per
   [Minimum CD session closure](https://migration.minimumcd.org/docs/agentic-cd/agent-configuration/)
   pattern).
3. **Use the template exactly.** Structured output enables machine parsing.
4. **Be concise.** The 150-word limit is a ceiling, not a target. Shorter is better. No filler phrases.

## Parse Arguments

Arguments: $ARGUMENTS

- `--from <json-file>`: Read review results from a JSON file (output
  of `/code-review --json`). If not provided, summarize from the
  most recent `/code-review` output in the conversation.

## Steps

### 1. Gather review data

If `--from` is specified, read the JSON file. Otherwise, look for
the most recent code review results in the current conversation
context.

Extract: overall status, agent statuses, issue counts by severity, and top issues.

### 2. Generate compact summary

Write a summary under 150 words following this template:

```markdown
## Review: <branch> @ <short-sha> — <date>

**Status**: <PASS|WARN|FAIL> (<N> agents, <N> issues)

**Findings**:
- <top 3-5 findings, one line each, severity prefix>

**Blocked by**: <agent names that returned fail, or "none">

**Action items**: <1-3 concrete next steps>
```

### 3. Save summary

Write the summary to `.claude/review-summaries/<date>-<short-sha>.md`.

Create the `.claude/review-summaries/` directory if it doesn't exist.

### 4. Report

Display the summary to the user. Note that it will be available as context in future sessions.
