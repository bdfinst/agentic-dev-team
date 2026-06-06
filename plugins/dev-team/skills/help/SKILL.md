---
name: help
description: >-
  List all available slash commands with their descriptions.
user-invocable: true
allowed-tools: Glob, Read
---

# Help

Role: worker. This command lists all available slash commands.

You have been invoked with the `/help` command.

Arguments: none.

## Worker constraints

1. List commands only; do not execute any.
2. Read from the command registry; do not invent commands.
3. **Be concise.** One line per command, no preamble.

## Steps

### 1. Find all command files

Use Glob to find all `skills/*/SKILL.md` files.

### 2. Extract name and description from each

Read each file's YAML frontmatter and extract the `name` and `description` fields.

### 3. Display as a formatted table

Sort commands alphabetically by name and display:

```
## Available Commands

| Command | Description |
|---------|-------------|
| /name   | description |
```

Omit any files that lack a `name` field in frontmatter (they may be non-command markdown files).
