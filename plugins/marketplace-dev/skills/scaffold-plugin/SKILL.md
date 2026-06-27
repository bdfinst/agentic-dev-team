---
name: scaffold-plugin
description: >-
  Create a new Claude Code plugin directory with the correct, audit-clean
  structure. Use when starting a new plugin in a marketplace monorepo, or when
  the user says "scaffold a plugin", "create a new plugin", "add a plugin to this
  marketplace", or "new plugin skeleton". Produces a directory that passes
  /plugin-audit with zero findings on a clean install.
argument-hint: "<plugin-name> [--dir plugins/<plugin-name>] [--description \"...\"]"
role: implementation
allowed-tools: Read, Write, Edit, Bash, Glob
---

# Scaffold Plugin

Role: implementation. Emit the shipped-plugin skeleton, then prove it clean.

## Constraints

1. **Name is a hard gate.** `<plugin-name>` must match `^[a-z][a-z0-9-]*$`. On a
   mismatch, emit the rule and a kebab-case suggestion, then stop.
2. **Never overwrite.** If the target dir already exists, report and stop.
3. **Only shipped files go under `plugins/<name>/`.** Tests, eval fixtures, and
   build tooling live at the repo root — never scaffold them inside the plugin.
4. **End on a green audit.** The deliverable is not the files; it is
   `/plugin-audit plugins/<name>` reporting zero findings.

## Step 1 — Parse and validate

- `NAME` = `$0`; validate against `^[a-z][a-z0-9-]*$` (Step constraint 1).
- `DIR` = `--dir` value, else `plugins/<NAME>`.
- `DESC` = `--description` value, else a one-line placeholder the user edits.
- If `DIR` exists → report and stop.

## Step 2 — Create the directory skeleton

```bash
mkdir -p "$DIR"/.claude-plugin "$DIR"/agents "$DIR"/skills "$DIR"/hooks "$DIR"/knowledge
```

`agents/`, `skills/`, `hooks/`, and `knowledge/` start empty. Git does not track
empty directories — add a `.gitkeep` to each so the skeleton survives commit:

```bash
for d in agents skills hooks knowledge; do : > "$DIR/$d/.gitkeep"; done
```

## Step 3 — Write the required files

**`$DIR/.claude-plugin/plugin.json`** — `version` starts at `0.1.0`; release-please
keeps it in sync thereafter (do not hand-bump):

```json
{
  "name": "<NAME>",
  "version": "0.1.0",
  "description": "<DESC>",
  "author": { "name": "", "email": "" }
}
```

**`$DIR/CLAUDE.md`** — plugin instructions that ship with the plugin: a one-line
purpose, a table of the plugin's `/commands` (empty to start), and the
conventions it enforces. Keep it small (it is always loaded).

**`$DIR/install.sh`** — the prerequisite checker with the Git-Bash-on-Windows
guard. Copy the canonical pattern from `${CLAUDE_PLUGIN_ROOT}/install.sh`
(checks `claude` + `jq`, warns on optional tools, detects Windows-without-Git-Bash
and points to https://git-scm.com/download/win), retitled for `<NAME>`. Then
`chmod +x "$DIR/install.sh"`.

**`$DIR/settings.json`** — hook registrations (empty `hooks` to start) plus a
`permissions` block:

```json
{
  "permissions": {
    "allow": ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "Agent", "Skill", "mcp__*"],
    "deny": ["Bash(rm *)", "Bash(git push *)"]
  }
}
```

## Step 4 — Register in the catalog (if a marketplace exists)

If `.claude-plugin/marketplace.json` exists at the repo root, add a plugin entry
(`name`, `description`, `source.path: "<DIR>"`, `source.source: "git-subdir"`,
`source.ref`, `version: "0.1.0"`) and add the matching release-please package +
manifest entry — see `/scaffold-marketplace` Step 4 for the exact block. If no
catalog exists, note that the user can create one with `/scaffold-marketplace`.

## Step 5 — Audit gate

Run `/plugin-audit <DIR>`. A fresh skeleton has no agents/skills, so the audit
must report **zero findings**. If it does not, fix the scaffold and re-run before
reporting success.

## Completion report

```text
Plugin scaffolded: <DIR>
Files: .claude-plugin/plugin.json, CLAUDE.md, install.sh, settings.json
Dirs:  agents/ skills/ hooks/ knowledge/
Audit: /plugin-audit <DIR> → zero findings
Next:  add agents with /agent-add, skills by hand or /agent-skill-authoring,
       eval fixtures with /init-plugin-eval <NAME>
```
