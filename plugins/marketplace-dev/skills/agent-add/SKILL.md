---
name: agent-add
description: >-
  Create a new Claude Code agent file (review or team type) following the
  official sub-agent schema and token-efficiency budgets. Use when the user
  wants to add a new review agent, detect a new category of code issue, create
  a team agent persona, or says things like "add an agent for X", "create a
  reviewer for Y", "new team agent for Z". Also use when given a URL to a
  coding standard that should become a review agent.
argument-hint: >-
  <description-or-url> [--plugin <dir>] [--name <name>] [--type review|team]
  [--model sonnet|opus|haiku|fable|inherit] [--effort low|medium|high|xhigh|max]
  [--memory user|project|local] [--isolation worktree] [--color <color>]
  [--max-turns <int>] [--background true|false] [--skills <name1,name2,...>]
  [--context diff-only|full-file|project-structure] [--lang <exts>] [--dry]
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, WebFetch, Skill(plugin-audit *)
---

# Agent Add

Role: implementation.

## Implementation constraints

1. Follow the official sub-agent schema and token budgets.
2. Delegate the build to the agent-create skill; do not improvise structure.
3. **Be concise.** Report the created agent file, no narration.

## Steps

### 1. Parse arguments

Capture the agent name/spec or URL from `$ARGUMENTS`.

### 2. Delegate

Invoke the agent-create skill with the arguments.

### 3. Report

Output the created file path.

Apply the guidelines defined in skills/agent-create/SKILL.md to the current
task. Read the skill file and follow its steps exactly.

If `$ARGUMENTS` starts with `http://` or `https://`, fetch the URL with
WebFetch first and extract the relevant guidance, then use that content as
the agent description.

Pass these flags through to the skill as context:

- `--plugin <dir>` → target plugin directory (resolved by agent-create Step 0)
- `--name <name>` → set agent name (skips name prompt)
- `--type review|team` → set agent type (skips type prompt)
- `--model sonnet|opus|haiku|fable|inherit|<full model ID>` → sets the agent's model (invalid values rejected against agent-contract.json)
- `--effort low|medium|high|xhigh|max` → sets the agent's reasoning effort (invalid values rejected against agent-contract.json)
- `--memory user|project|local` / `--isolation worktree` / `--color <color>` / `--max-turns <int>` / `--background true|false` / `--skills <name1,name2,...>` → optional native fields, no forced defaults
- `--context diff-only|full-file|project-structure` → sets `Context needs:` field
- `--lang <exts>` → adds language scope declaration to the body
- `--dry` → show generated content without writing to disk or updating registry

Apply this skill to: $ARGUMENTS
