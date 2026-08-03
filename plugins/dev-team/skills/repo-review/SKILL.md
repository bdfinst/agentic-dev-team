---
name: repo-review
description: >-
  Whole-repository drift review for the review agents that a per-diff
  /code-review pass cannot meaningfully evaluate — accumulated file/CLAUDE.md
  size drift, AI-provenance verification debt, harness-config completeness,
  and cross-file frontend component duplication. Use when the user asks for a
  "repo review", "drift review", "whole-tree review", wants to check
  accumulated size/token drift, verification debt, or duplicated frontend
  components across the WHOLE codebase rather than a single diff, or
  periodically (e.g. every N merged PRs) to catch drift no single diff-scoped
  review would surface. Report-only — never gates a commit.
argument-hint: "[--path <dir>] [--json] [--pdf]"
user-invocable: true
allowed-tools: Read, Write, Grep, Glob, AskUserQuestion, Agent, Bash(git rev-list *), Bash(git rev-parse *), Bash(sh *)
---

# Repo Review

Role: orchestrator. Route work to review agents; do not review code yourself.

**Why this skill exists (#1733, #1735).** `/code-review` dispatches its panel
per diff. Four agents' findings are properties of the *whole tree* — absolute
size, accumulated drift, or the full component inventory — not of any single
diff's delta, so a diff-scoped pass either can't see the pattern they exist to
catch (a file that crept past a size threshold over 10 separate small PRs) or
re-derives a whole-codebase judgment independently on every review. This
skill runs those four agents against the whole repository instead, on a
cadence the operator controls (manual invocation today — see "Cadence" below),
and writes a report rather than gating anything.

**Not `/code-review`.** No staging, no gate-hash, no `.review-passed` write,
no interactive fix loop, no pre-flight lint/typecheck/secret-scan gates —
there is no commit to gate. This is a read-only report, structurally closer
to `/harness-audit`/`/co-evolution-audit` than to `/code-review`.

## Orchestrator constraints

1. **Do not review code yourself.** Delegate all analysis to the four agents below.
2. **Fixed roster — not resolver-selected.** Unlike `/code-review`'s `select_lenses.py`-driven panel, this skill's roster is fixed and unconditional (see Roster). Do not add or drop agents based on file type; each agent's own `## Skip` clause handles the case where it has nothing to say.
3. **Write the report to a file.** Present only the summary table and next-steps in chat — do not repeat the full report.
4. **Be concise.** Tables and JSON, no preambles, no filler.

## Parse Arguments

Arguments: $ARGUMENTS

| Flag | Behavior |
| --- | --- |
| `--path <dir>` | Review only files under this directory (still whole-subtree, not a diff) |
| `--json` | Emit aggregated JSON to stdout instead of prose; writes no report file |
| `--pdf` | After the report is written, render a sibling PDF via `hooks/lib/report_pdf.py`. No-op under `--json` (no report file is written) |
| (no flags) | Review the whole repository |

## Steps

### 1. Determine target files

`--path <dir>`: `Glob("<dir>/**/*")`, excluding `node_modules`, `.git`, `dist`, `build`, `coverage`. No `--path`: the whole repository, same exclusions. **Never `Read` a directory path directly** — `Read` on a directory throws `EISDIR`; always enumerate with `Glob`. See `${CLAUDE_PLUGIN_ROOT}/knowledge/directory-enumeration.md`.

**Scope validation** (mirrors `/code-review`'s own table, without its sliced-mode machinery — that is a `--path`-narrowing hint here, not an auto-engaged mode):

| File count | Action |
| --- | --- |
| ≤500 | Proceed |
| >500 | Warn: "Reviewing {N} files — consider `--path` to narrow scope, or expect a slower, larger-context pass." Proceed anyway — this skill has no sliced-mode equivalent to fall back to. |

### 2. Load drift state

Read `.claude/memory/repo-review-state.json` if it exists: `{"last_commit": "<sha>", "last_run_at": "<ISO 8601>"}`.

**Validate `last_commit` before it touches a shell command — this file is not trusted input.** It is written by step 7 below, but nothing stops a hostile PR from committing its own `.claude/memory/repo-review-state.json` (see step 7's `.gitignore` note) with an arbitrary string in `last_commit`, which a maintainer's later `/repo-review` run would then read. Treat any value that does not match `^[0-9a-fA-F]{7,40}$` exactly like "no prior state" — do not interpolate it into a command. Only once it matches that pattern, confirm it is actually reachable and count commits since it, in one call with no pipe:

```bash
git rev-list --count "<validated-sha>"..HEAD
```

A non-zero exit (unreachable commit — e.g. history was rewritten) is the same "no prior state" case as a missing file: carry `null` for the drift count, not an error. Carry the count (or `null` if there is no prior state, the repo is not a git repository, `last_commit` failed validation, or it is no longer reachable) into the report as the drift signal. This is informational only — it does not gate or skip anything, and a missing/unreadable/invalid state file is not an error, just "first run."

**Known limitation, accepted by design:** the read here (step 2) and the write in step 7 are not atomic. Two `/repo-review` invocations racing on the same repository can lose one's drift-state update to the other. Since the count is informational only — never gating or blocking anything — this is an accepted limitation, not a defect to fix: at most it costs one run's drift signal, never a wrong review result.

**Cadence (#1735 non-goal, addressed minimally here).** This skill is
invoked manually — there is no scheduled trigger, matching the existing
`/harness-audit` and `/co-evolution-audit` precedent of pure on-demand
invocation rather than a cron-style mechanism. The commits-since-last-audit
count above is what lets an operator decide *for themselves* whether enough
has changed to be worth another pass (or wire it into their own CI cadence,
e.g. "run every 50 merged PRs") without this skill inventing a scheduler.

### 3. Confirm agent-dispatch capability

Before dispatching anything, confirm the `Agent`/`Task` tool is present in this toolset. If it is not: **STOP.** Do not review the files yourself as a substitute — report which capability is missing and that this skill cannot run until re-invoked from a session that has it. Do not write a report claiming a review ran.

### 4. Dispatch the fixed roster

Spawn all four as parallel subagents in a single message using the `Agent` tool. Every one of these was **removed from `/code-review`'s per-diff panel** for the same reason (#1733) — do not re-add them there; this skill is where they run now.

| Agent | Why whole-tree, not per-diff |
| --- | --- |
| `token-efficiency-review` | File length, CLAUDE.md size, LLM anti-patterns are properties of absolute size/drift, invisible to a single diff |
| `ai-provenance-review` | "Verification debt" and "regeneration risk" are trend/accumulation metrics by definition |
| `claude-setup-review` | Reviews the harness (CLAUDE.md, rules, skills, agent frontmatter), not the changeset |
| `component-architecture-review` | Cross-file duplication/reusable-component extraction is best judged against the *entire* component inventory. **Note:** this agent also stays in `/code-review`'s per-diff panel, narrowed to newly-*added* component files only (`Scope: added-only`, #1733) — its dispatch here is unconditional and independent of that narrower rule. |

**Context payload**: enumerate the target files and directory tree once (step 1 already did this) and pass the same full files + tree to every agent — no diff exists to describe, so there is no changed-file list to pass, unlike `/code-review`'s `project-structure` payload. Pass each agent's declared `model:`/`effort:` frontmatter unchanged, per `agents/orchestrator.md` → Model/Effort Resolution (ADR 0026). Skip an agent's dispatch only if step 1's target set is empty.

**Per-agent output**: the shared contract in [`../../knowledge/review-agent-output-contract.md`](../../knowledge/review-agent-output-contract.md), wrapped with `agentName`/`modelTier` — same envelope `/code-review` uses, so tooling that already parses one parses the other.

Wait for all four to complete before aggregating.

### 5. Aggregate and score

Consolidate findings the same way `/code-review` step 5c does: when multiple agents flag the same `file:line`, one `topFindings` entry with `severity` = the highest single enum, `agents` = the reporting agents array. No slash/comma-joined severities.

Score overall health with the general-case formula from [`../../knowledge/review-rubric.md`](../../knowledge/review-rubric.md) § Health Score Calculation (0 fail AND ≤2 warn = 🟢; 1-2 fail OR 3+ warn = 🟠; 3+ fail = 🔴) — the rubric's category-weight table names other agents and does not apply here; use only the general pass/warn/fail counting rule. `skip` results are excluded from scoring, same as `/code-review`.

### 6. Generate report

**`--json`**: emit the aggregated JSON object (same shape as `/code-review`'s `--json` output — see [`../code-review/output-format.md`](../code-review/output-format.md#aggregated-json-result-json-flag), plus a top-level `commitsSinceLastAudit` field from step 2) to **stdout**. Write no file. Stop — do not proceed to step 7.

**Otherwise**, emit a prose summary:

```
# Repo Review — <date>

Scope: <whole repository | `--path <dir>`>
Commits since last audit: <N | "first run">

## Health: <🟢|🟠|🔴>

| Agent | Status | Issues |
| --- | --- | --- |
| token-efficiency-review | ... | ... |
| ai-provenance-review | ... | ... |
| claude-setup-review | ... | ... |
| component-architecture-review | ... | ... |

## Top Findings

<topFindings table — file:line, severity, agents, message>
```

### 7. Write the report and update drift state

**Skip this step entirely if `--json`** (already stopped in step 6).

Write the prose summary to `.dev-team-reports/repo-review.md`, creating the directory if absent, overwriting any existing file — write it even when every agent passed clean. Print `Report written: .dev-team-reports/repo-review.md` (or `(replaced previous run)` when a file already existed). A write failure (permission/read-only) is non-fatal: report `Cannot write .dev-team-reports/repo-review.md: <error>` and continue.

Then, if the target was a git repository, update the drift state for next run: run `git rev-parse HEAD` and write `.claude/memory/repo-review-state.json` (creating `.claude/memory/` if absent) as `{"last_commit": "<that sha>", "last_run_at": "<current ISO 8601 timestamp>"}`, overwriting any prior state. If the target is not a git repository, skip this write — there is no commit to anchor the next drift count to.

**This repository's own `.gitignore` covers that path already** (step 2's trust-boundary note relies on it). A downstream project running this skill from the plugin should add an equivalent ignore rule for `.claude/memory/repo-review-state.json` — it is a per-run, regeneratable artifact, and leaving it trackable reopens the exact commit-and-plant precondition step 2 defends against.

**`--pdf`**: when passed and a report file was written this run, render it per `knowledge/report-pdf-integration.md`:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/repo-review.md
```

No-op (state the reason, do nothing else) when no report file was written this run.
