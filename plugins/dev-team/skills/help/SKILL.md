---
name: help
description: >-
  List the main dev-team workflows, with an option to show every
  user-invocable slash command.
argument-hint: "[--all]"
user-invocable: true
allowed-tools: Glob, Read
---

# Help

Role: worker. This command lists dev-team slash commands.

You have been invoked with the `/help` command.

Arguments: `[--all]` — omit for the curated main-workflow list; pass `--all` for every user command.

## Worker constraints

1. List commands only; do not execute any.
2. Read from the command registry; do not invent commands.
3. **Be concise.** One line per command, no preamble.

## Steps

### 1. Choose a mode

No arguments → [Main workflows](#2-main-workflows-default). `--all` → [All commands](#3-all-commands---all).

### 2. Main workflows (default)

Display this fixed, curated table — the primary spec → plan → build → review →
ship pipeline plus the commands most sessions need. This list is curated, not
derived from the filesystem; do not add or remove rows without a corresponding
edit to this file.

```
## Main Workflows

| Command | What It Does |
|---------|-------------|
| `/ship` | Run the full spec → plan → build → review → PR pipeline in one command |
| `/specs` | Capture Intent, Architecture Notes, and Acceptance Criteria before planning |
| `/plan` | Decompose a feature into vertical slices with Gherkin scenarios |
| `/build` | Implement an approved plan in small, reviewed batches |
| `/code-review` | Run the review agents against a changeset and auto-fix issues |
| `/pr` | Run pre-PR quality gates and open a pull request |
| `/test-improve` | Analyze and raise a repo's test coverage and health |
| `/triage` | Investigate a bug and write a TDD fix plan |
| `/setup` | Provision a repo for the dev-team plugin |
| `/continue` | Resume work from a prior session |
| `/help` | Show this list — pass `--all` for every command |

Run `/help --all` to see every available command.
```

### 3. All commands (`--all`)

1. Use Glob to find every `skills/*/SKILL.md` file.
2. Read each file's YAML frontmatter and extract `name`, `description`, and `user-invocable`.
3. Keep only files where `user-invocable` is `true` and `name` is present — agent-loaded skills are not user commands and must not appear.
4. Sort the remaining commands alphabetically by name and display:

```
## Available Commands

| Command | Description |
|---------|-------------|
| /name   | description |
```
