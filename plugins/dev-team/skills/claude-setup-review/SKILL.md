---
name: claude-setup-review
description: >-
  Audit this project's Claude Code harness — CLAUDE.md completeness, rule
  clarity, skill and agent wiring, path accuracy, and agent frontmatter schema
  compliance. Use when the user says "review my CLAUDE.md", "audit my Claude
  setup", "is my Claude config right", "check my agent frontmatter", "are my
  skill paths correct", or after adding or restructuring CLAUDE.md, agents, or
  skills. Advisory — it recommends, it does not edit.
argument-hint: "[--path <dir>] [--json]"
user-invocable: true
allowed-tools: Read, Grep, Glob, Skill, Agent
---

# Claude Setup Review

Role: orchestrator. This command dispatches the `claude-setup-review` agent
over the project's Claude Code configuration and aggregates one report. It does
not edit configuration itself — it coordinates.

## Why this is a command and not a review lens

This agent reviews the **harness**, not the changeset. Its subject — CLAUDE.md,
`.claude/`, agent frontmatter, skill wiring — is almost never what a diff
touches, so as an automatic `/code-review` lens it was dead weight: `Scope:
always` put it in an 18-lens panel for a two-file JavaScript change in a project
with no Claude configuration at all. Harness quality is real, but it changes on
its own schedule, so it gets its own command instead of a seat in every review.

`/code-review` therefore does **not** dispatch this agent. Run this command
after adding or restructuring CLAUDE.md, agents, or skills, or periodically as a
health check.

Related but distinct:

- [`/agent-audit`](../agent-audit/SKILL.md) checks **structural compliance** of
  this plugin's own agents, skills, and hooks — a mechanical conformance gate.
- This command reviews **your project's** Claude setup for completeness and
  clarity, which is a judgement call.
- [`/agent-readiness`](../agent-readiness/SKILL.md) scores the whole repository
  against the Agent-Readiness Scorecard; this command is narrower and deeper on
  the configuration itself.

This command is executed under orchestrator direction. Dispatch the agent with
its `model:`/`effort:` frontmatter as declared — the harness resolves both
fields natively before dispatch, per Model/Effort Resolution in
`agents/orchestrator.md` (ADR 0026).

## Orchestrator constraints

1. **Advisory only.** Aggregate findings and recommendations. Do not edit
   CLAUDE.md, agent files, or skill files. Hand actionable fixes to
   `/apply-fixes` or make them yourself only on explicit instruction.
2. **Report absence plainly.** A project with no Claude configuration is a
   valid finding ("no CLAUDE.md — agents have no project context"), not an
   error. Never invent configuration that should exist without saying why.
3. **No double-reporting.** This review owns configuration completeness and
   accuracy. Defer prose quality to `doc-review`, token budgets to
   `token-efficiency-review`, and this plugin's own structural conformance to
   `/agent-audit`. When a finding belongs to one of those, drop it here.
4. **Be concise.** One aggregated report. Issue messages one sentence;
   recommendations map to a concrete next edit.

## Parse Arguments

Arguments: $ARGUMENTS

Optional:

- `--path <dir>`: project root to audit (default: current working directory)
- `--json`: emit the agent's aggregated JSON instead of prose (for CI)

## Steps

### 1. Determine target files

Collect the project's Claude configuration from the target root:

- `CLAUDE.md` and any nested `**/CLAUDE.md`
- `.claude/settings.json`, `.claude/settings.local.json`
- `.claude/agents/*.md`, `.claude/skills/**/SKILL.md`
- `.claude/hooks/**`, **excluding** `.claude/hooks/freeze-state.json` and
  `.claude/hooks/careful-state.json` — plugin-written runtime state
  (`/freeze`/`/unfreeze`/`/careful`/`/guard`), not operator-authored hook
  code; see [`docs/python-hook-contract.md`](../../../../docs/python-hook-contract.md)
  § Environment variables (issue #1904 item 10)
- `README.md` only where it documents agent or contributor workflow

Enumerate with `Glob`, never a directory `Read` (it throws `EISDIR`) — see
[`../../knowledge/directory-enumeration.md`](../../knowledge/directory-enumeration.md).

If none of these exist, emit
`No Claude Code configuration found — nothing to review. Consider /project-init.`
and stop.

### 2. Dispatch

Dispatch the `claude-setup-review` agent once, passing the collected file list.
If `REVIEW-CONTEXT.md` exists at the project root, pass its contents too,
prefixed with `Institutional context provided for this review:`.

### 3. Report

Emit the agent's findings per
[`../code-review/output-format.md`](../code-review/output-format.md), grouped by
severity. With `--json`, emit the aggregated JSON object to **stdout** and write
no file — that object is the only output for the run.

Without `--json`, write the prose report to
`.dev-team-reports/claude-setup-review.md` in the target project's working
directory, repo-relative — never prepend a scratchpad or session root — and
confirm with one line: `Report written: .dev-team-reports/claude-setup-review.md`.
If the write fails, report the error in chat and continue unaffected.
