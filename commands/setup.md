---
name: setup
description: >-
  Detect a project's tech stack and auto-generate project-level CLAUDE.md,
  PostToolUse hooks, and language-specific agent templates in one shot. Use
  this when onboarding a new project, or when the user says "setup",
  "bootstrap", "configure this project", or "detect my stack".
argument-hint: "[--dry-run]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(jq *), Bash(ls *), Bash(mkdir *), Bash(cat *), Bash(test *), Bash(node *)
---

# Project Setup

Role: orchestrator. This command bootstraps project-level configuration by detecting the tech stack and generating appropriate files.

You have been invoked with the `/setup` command.

## Parse Arguments

Arguments: $ARGUMENTS

- `--dry-run`: Report what would be created without writing any files.

## Steps

### 1. Detect tech stack

Search the project root for manifest files and record findings:

| Indicator file | Stack |
|----------------|-------|
| `package.json` | Node/JavaScript |
| `tsconfig.json` | TypeScript |
| `pyproject.toml`, `requirements.txt`, `setup.py` | Python |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `Gemfile` | Ruby |
| `pom.xml`, `build.gradle`, `build.gradle.kts` | Java/Kotlin |
| `*.csproj`, `*.sln` | C#/.NET |
| `angular.json` | Angular |
| `Dockerfile`, `docker-compose.yml` | Container |

Also detect frameworks within each stack:
- **Node**: check `package.json` dependencies for `react`, `vue`, `svelte`, `@angular/core`, `express`, `fastify`, `nestjs`, `next`, `vitest`, `jest`, `mocha`
- **Python**: check for `django`, `flask`, `fastapi`, `pytest` in deps
- **Go**: check for `gin`, `echo`, `fiber` in `go.mod`

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

### 2. JS/TS-specific flow

If a JavaScript or TypeScript project is detected:

1. **ES Modules check**: Read `package.json` and verify `"type": "module"` is set. If missing, report it and ask the user whether to add it.
2. **TypeScript check**: If `package.json` exists but `tsconfig.json` does not, ask: "This is a JavaScript project. Would you like to add TypeScript?" If yes, scaffold a `tsconfig.json` with strict mode and note that `ts-enforcer` template should be activated.
3. **Require/module.exports scan**: Run a quick grep for `require(` and `module.exports` in source files (exclude `node_modules`). Report any findings as migration candidates.
4. Always mark `functional-patterns` and `esm-enforcer` templates for activation.

### 3. Select agent templates

Based on detected stack, select applicable templates from `templates/agents/`:

| Template | Condition |
|----------|-----------|
| `ts-enforcer` | `tsconfig.json` exists or TypeScript in deps |
| `esm-enforcer` | Any JS/TS project (always-on) |
| `functional-patterns` | Any JS/TS project (always-on) |
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

Based on detected stack, generate the appropriate PostToolUse hook entry for the project's `.claude/settings.json`. Use the formatting table:

| Stack | Extensions | Formatter command |
|-------|-----------|-------------------|
| Node/TypeScript | `.ts`, `.tsx`, `.js`, `.jsx` | `npx prettier --write "$FILE" && npx eslint --fix "$FILE"` |
| Python | `.py` | `ruff format "$FILE" && ruff check --fix "$FILE"` |
| Go | `.go` | `gofmt -w "$FILE"` |
| Rust | `.rs` | `rustfmt "$FILE"` |
| Ruby | `.rb` | `bundle exec rubocop -A "$FILE"` |
| Java/Kotlin | `.java`, `.kt` | `google-java-format -i "$FILE"` / `ktlint -F "$FILE"` |
| C# | `.cs` | `dotnet format --include "$FILE"` |

Only include branches for the detected stack. Verify the formatter tool is installed before adding it (check `npx prettier --version`, `ruff --version`, etc.). If not installed, warn the user.

### 6. Generate /pr command

Create a project-specific `commands/pr.md` if one doesn't exist, referencing the project's test/lint/typecheck commands.

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
- Activated templates: ts-enforcer, esm-enforcer, functional-patterns, react-testing

### Recommendations
- Add `"type": "module"` to package.json
- 3 files using `require()` — consider migrating to ES imports
```

If `--dry-run` was specified, prefix the report with "**DRY RUN** — no files were written." and skip all writes.
