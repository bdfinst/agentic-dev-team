---
name: setup
description: >-
  Generate dev-team-specific project configuration — project-level CLAUDE.md,
  the PostToolUse formatting hook, language-specific agent template
  activation, and a generated `/pr` command — from the stack signal
  `/dev-team:project-init` already established. This is NOT where toolchain
  detection/installation lives (that's `/project-init`); `/setup` only
  consumes it. Use this when onboarding a new project to the dev-team
  plugin's own config, or when the user says "setup", "bootstrap", "configure
  this project for dev-team", or "activate agent templates".
argument-hint: "[--dry-run]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(jq *), Bash(ls *), Bash(mkdir *), Bash(cat *), Bash(test *), Bash(node *)
---

# Project Setup

Role: orchestrator. This command bootstraps dev-team-specific project
configuration — CLAUDE.md, the PostToolUse formatting hook, agent template
activation, and the generated `/pr` command. It delegates all tech-stack
detection and toolchain install/inventory work to `/dev-team:project-init`,
which is the canonical source of truth for that; `/setup` never re-derives it.

You have been invoked with the `/setup` command.

## Orchestrator constraints

1. Detect and scaffold; delegate generation, do not review code yourself.
2. Do not overwrite existing project config without confirming.
3. **Be concise.** Report detected stack and generated artifacts, no narration.

## Parse Arguments

Arguments: $ARGUMENTS

- `--dry-run`: Report what would be created without writing any files.

## Steps

### 1. Invoke `/dev-team:project-init` for stack detection and toolchain

Run `/dev-team:project-init` first. It owns all tech-stack detection,
tool inventory, the three-column confirm plan, and installation (JS/TS
scaffold, Python/C#/Java lane tools, capability tools, graph-tools). Let it
run to completion — including its own user confirmation gate — before
continuing.

### 2. Record the stack signal for dev-team's own use

`/setup` still needs a small, cheap signal of its own to populate
`.claude/project-stack.json` and to drive Step 3's template selection. Reuse
project-init's documented detection-signal table
(`skills/project-init/SKILL.md` Step 1 and Step 2) by reference rather than
re-deriving a second independent detection pass — probe for the same
indicator files project-init already classified (`package.json`,
`tsconfig.json`, `pyproject.toml`/`requirements*.txt`, `*.csproj`/`*.sln`,
`pom.xml`/`build.gradle*`) plus the handful of framework dependency checks
(`react`, `vue`, `svelte`, `@angular/core`, `next`, `django`, `flask`,
`fastapi`) that project-init's stack table doesn't itself need to record.

Write findings to `.claude/project-stack.json`:

```json
{
  "detected": "2026-03-18",
  "stacks": ["typescript", "node"],
  "frameworks": ["react", "vitest"],
  "packageManager": "npm|yarn|pnpm|bun",
  "hasDocker": true,
  "indicators": {
    "package.json": true,
    "tsconfig.json": true
  }
}
```

This step does not install anything and does not repeat project-init's
JS/TS ES-module/TypeScript/require-scan checks or its formatter-selection
logic — those are entirely project-init's job (Step 4/Scaffold steps and
Step 4b/4c there). It only records the signal `/setup` needs for its own
template selection below.

### 3. Select agent templates

Based on detected stack, select applicable templates from `templates/agents/`:

| Template | Condition |
|----------|-----------|
| `ts-enforcer` | `tsconfig.json` exists or TypeScript in deps |
| `esm-enforcer` | Any JS/TS project (always-on) |
| ~~`functional-patterns`~~ | ~~Any JS/TS project~~ — **deprecated**, superseded by `js-fp-review` agent |
| `react-testing` | `react` or `react-dom` in deps |
| `front-end-testing` | Any frontend framework (React, Vue, Svelte, Angular) |
| `twelve-factor-audit` | Has Dockerfile, server entry point, or cloud config |
| `python-quality` | Python stack detected |
| `go-quality` | Go stack detected |
| `csharp-quality` | C#/.NET stack detected |
| `angular-testing` | `@angular/core` in deps |

Present the list to the user and ask for confirmation before scaffolding.

### 4. Generate project-level CLAUDE.md

If `.claude/CLAUDE.md` does not already exist in the target project, generate one containing:

- Project name and detected stack summary
- Discovered conventions (formatter, linter, test runner)
- References to activated agent templates
- Build/test/lint commands detected from `package.json` scripts, `Makefile`, etc.

If `.claude/CLAUDE.md` already exists, ask whether to merge or skip.

### 5. Generate PostToolUse formatting hook

Wire a PostToolUse hook entry for the project's `.claude/settings.json` that
runs the formatter for the detected stack, mapped by extension (Node/TS →
prettier + eslint, Python → ruff, Go → gofmt, Rust → rustfmt, Ruby →
rubocop, Java/Kotlin → google-java-format/ktlint, C# → dotnet format). The
tool itself is `/project-init`'s responsibility to install — since Step 1
already ran it, the formatter should be present. Only if a formatter is
still missing (check e.g. `npx prettier --version`, `ruff --version`), warn
the user and re-point them at `/project-init` rather than installing it here.

### 6. Generate /pr command

Create a project-specific `skills/pr/SKILL.md` if one doesn't exist, referencing the project's test/lint/typecheck commands.

### 7. Report

Display a summary of everything created:

```
## Setup Complete

**Stack**: TypeScript, React, Vitest
**Package manager**: pnpm

### Created
- `.claude/project-stack.json` — stack detection results
- `.claude/CLAUDE.md` — project conventions
- `.claude/settings.json` — PostToolUse formatting hook (prettier + eslint)
- Activated templates: ts-enforcer, esm-enforcer, react-testing

### Recommendations
- Add `"type": "module"` to package.json
- 3 files using `require()` — consider migrating to ES imports
```

If `--dry-run` was specified, prefix the report with "**DRY RUN** — no files were written." and skip all writes.
