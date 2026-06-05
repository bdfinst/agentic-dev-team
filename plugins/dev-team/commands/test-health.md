---
name: test-health
description: >-
  Project-wide test-strategy audit: derive the suite's shape and
  shape-vs-architecture fit, map coverage to the Agile Testing Quadrants, roll
  up coverage + mutation health, flag flaky tests and automation maturity, and
  produce an ordered improvement plan. Delegates CD-determinism + pipeline
  assessment to cd-test-architecture. Use when the user says "audit our tests",
  "test-health", "how healthy is our test suite", or "test strategy review".
  Advisory — it writes a report, it does not edit.
argument-hint: "[--path <dir>]"
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git *), Skill, Agent
---

# Test Health

Role: orchestrator. This command is a thin entry point: it parses arguments and
runs the [`test-health`](../skills/test-health/SKILL.md) skill, which performs
the audit and writes the report. It does not analyze files itself.

This command is executed under orchestrator direction. Any agents the skill
dispatches carry their tier alias (from their `model:` frontmatter); the
PreToolUse hook `hooks/agent-model-resolve.sh` resolves it per the Resolution
Procedure in `agents/orchestrator.md`.

## Orchestrator constraints

1. **Advisory only.** The audit writes a report; it does not edit code or tests.
   Hand mechanical fixes to `/apply-fixes`, refactors to `/plan` or `/build`.
2. **Delegate, don't re-derive.** Architecture/pipeline assessment comes from
   `cd-test-architecture` — the skill summarizes it, never contradicts it.
3. **Be concise.** Surface the report path and the top findings in chat; the
   detail lives in the report file.

## Parse Arguments

Arguments: $ARGUMENTS

- `--path <dir>`: target repository/subtree to audit (default: current working
  directory).

## Steps

Invoke the `test-health` skill on the resolved target. The skill:

1. Asks one **non-blocking** pain-point question, then proceeds without waiting.
2. **Short-circuits** trivial suites (tiny, no shape pathology, clear
   conventions) to a one-paragraph summary.
3. Otherwise produces the full diagnostic and writes
   `reports/test-health-<date>.md`.

Advisory only — surface the report path and the top findings in chat. Hand
mechanical fixes to `/apply-fixes` and refactors to `/plan` or `/build`.
