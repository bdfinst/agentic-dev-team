---
name: frontend-architecture
description: >-
  Frontend component architecture review — dispatch the
  component-architecture-review agent over the frontend component files to catch
  reusable components that should be extracted, duplicated UI patterns, prop
  drilling, component-granularity problems, and inconsistent component APIs as a
  frontend evolves. Use when the user says "review the frontend architecture",
  "are my components reusable", "is this UI duplicated", "should this be a shared
  component", "check for prop drilling", or before extracting a component library.
  Advisory — it recommends, it does not edit.
argument-hint: "[--path <dir>] [--since <ref>] [--all] [--json]"
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(git log *), Skill, Agent
---

# Frontend Architecture

Role: orchestrator. This command scopes the changeset to frontend component
files and dispatches the `component-architecture-review` agent, then aggregates
one report. It does not review files itself — it coordinates.

This command is executed under orchestrator direction. Dispatch the agent with
its effort band (from its `effort:` frontmatter); the PreToolUse hook
`hooks/agent_model_resolve.py` resolves it to the active snapshot per the
Resolution Procedure in `agents/orchestrator.md`.

## Orchestrator constraints

1. **Advisory only.** Aggregate findings and recommendations. Do not edit
   component code. Hand actionable fixes to `/apply-fixes` or `/build`.
2. **Scope to the frontend.** Only pass frontend component files to the agent;
   skip the run with a one-line note if none are in scope.
3. **No double-reporting.** This review owns component *reuse and composition*.
   Defer accessibility to `a11y-review`, framework reactivity to `svelte-review`
   (and other framework agents), non-UI logic duplication and SRP/coupling to
   `structure-review`/`refactor-opportunity-review`, and naming to
   `naming-review`. When the same line belongs to one of those, drop it here.
4. **Be concise.** One aggregated report. Issue messages one sentence;
   recommendations map to a concrete next edit (extract X, lift Y to context).

## Parse Arguments

Arguments: $ARGUMENTS

Optional:

- `--path <dir>`: target directory (default: current working directory)
- `--since <ref>`: target files changed since a git ref (`git diff --name-only <ref>...HEAD`)
- `--all`: review all frontend component files in the repository
- `--json`: emit the agent's aggregated JSON instead of prose (for CI)

## Steps

### 1. Determine target files

Same auto-scope logic as `/code-review`: review uncommitted changes if any
exist, else the full repository; honor `--since`, `--path`, and `--all`. Then
keep only frontend component files — `.jsx`, `.tsx`, `.vue`, `.svelte`, Angular
`*.component.ts` and their templates, and `.js`/`.ts` modules that render UI.
Exclude `node_modules`, `dist`, `build`, and test files.

If no frontend component files are in scope, emit
`No frontend component files in scope — nothing to review.` and stop.

### 2. Dispatch the review agent

Spawn `component-architecture-review` as a sub-agent in a single batch, passing
the in-scope files as full files (`Context needs: full-file`). It returns its
standard JSON (`status`/`issues`/`summary`). If it skips, report that and stop.

### 3. Aggregate and rank

Take the agent's issues. Rank: semantic UI duplication and prop-drilling that
force multi-site edits first (`error`), then high-value extraction and
granularity fixes (`warning`), then composition and API-consistency cleanups
(`suggestion`). Group by file. Drop any finding that belongs to another agent
per constraint 3.

### 4. Report

If `--json`, emit the aggregated JSON object and stop. Otherwise produce one
report (chat for a small target; `reports/frontend-architecture-<date>.md` for a
module):

```markdown
## Frontend Architecture Review — <target>

**Health**: <pass|attention|critical>   **Component files**: N   **Findings**: N

### Findings (by severity)
| File:line | Issue | Severity | Suggested fix |

### Extraction & composition recommendations
<reusable components to extract, prop-drilling to lift, APIs to align, missing or
stale component-library `index` barrel to add — each with the concrete next edit>

### Next steps
- Mechanical fixes (extract component, call existing primitive) → /apply-fixes
- Larger refactors (lift state, recompose) → /plan or /build
```

Surface only what's actionable. If everything is clean, say so in one line.
