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

## Steps

### 1. Find all command files

Use Glob to find all `commands/*.md` files.

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
