---
name: scaffold-marketplace
description: >-
  Create a Claude Code plugin-marketplace root with a valid catalog, release
  automation, and at least one plugin slot. Use when starting a new marketplace
  monorepo, or when the user says "scaffold a marketplace", "set up a plugin
  marketplace", "create a marketplace catalog", or "bootstrap a marketplace repo".
argument-hint: "<owner-handle> [--first-plugin <name>]"
role: implementation
allowed-tools: Read, Write, Edit, Bash, Glob
---

# Scaffold Marketplace

Role: implementation. Lay down the marketplace catalog and the release wiring
that keeps it in sync, then seed at least one plugin slot.

## Constraints

1. **Catalog format is fixed.** `.claude-plugin/marketplace.json` must match the
   structure in `docs/marketplace-builder-plugin-playbook.md` §2.1 — `name`,
   `owner`, and a `plugins[]` array of `git-subdir` source entries.
2. **At least one plugin slot.** A marketplace with no plugins is not done;
   scaffold a first plugin entry (via `--first-plugin` or a placeholder slot).
3. **Versioning is automated, never hand-edited.** Every catalog entry's
   `version` and `source.ref` are owned by release-please `extra-files`. Do not
   ask the user to maintain them by hand.
4. **Never overwrite an existing catalog.** If `.claude-plugin/marketplace.json`
   exists, report and stop (offer `/scaffold-plugin` to add a plugin instead).

## Step 1 — Parse

- `OWNER` = `$0` (the marketplace `name` / owner handle).
- `FIRST` = `--first-plugin` value, else `example-plugin` (a placeholder slot the
  user renames).
- If `.claude-plugin/marketplace.json` exists → stop.

## Step 2 — Write the catalog

**`.claude-plugin/marketplace.json`:**

```json
{
  "metadata": { "description": "<one-line marketplace description>" },
  "name": "<OWNER>",
  "owner": { "name": "<OWNER full name>" },
  "plugins": [
    {
      "author": { "name": "<OWNER full name>" },
      "description": "<FIRST plugin description>",
      "homepage": "https://github.com/<org>/<repo>",
      "license": "MIT",
      "name": "<FIRST>",
      "repository": "https://github.com/<org>/<repo>",
      "source": {
        "path": "plugins/<FIRST>",
        "ref": "<FIRST>-v0.1.0",
        "source": "git-subdir",
        "url": "https://github.com/<org>/<repo>.git"
      },
      "version": "0.1.0"
    }
  ]
}
```

Each entry's `version` and `source.ref` stay in lock-step with the plugin's own
`plugin.json` and its release tag — wired in Step 4, never hand-edited.

## Step 3 — Scaffold the first plugin

Invoke `/scaffold-plugin <FIRST>` to create `plugins/<FIRST>/` with its required
files and dirs. (If the user passed no `--first-plugin`, scaffold the placeholder
and tell them to rename it.)

## Step 4 — Wire release automation

**`.release-please-manifest.json`** — one entry per plugin at its current version:

```json
{ "plugins/<FIRST>": "0.1.0" }
```

**`release-please-config.json`** — `include-v-in-tag` + `include-component-in-tag`
true, and one `packages` entry per plugin. Each plugin versions **independently**
(its own `component`, tag prefix, and manifest entry); `extra-files` rewrite the
catalog on release so `plugin.json`, the tag, and `marketplace.json` never drift:

```json
"plugins/<FIRST>": {
  "release-type": "simple",
  "package-name": "<FIRST>",
  "component": "<FIRST>",
  "extra-files": [
    ".claude-plugin/plugin.json",
    { "type": "json", "path": "/.claude-plugin/marketplace.json",
      "jsonpath": "$.plugins[?(@.name=='<FIRST>')].version" },
    { "type": "json", "path": "/.claude-plugin/marketplace.json",
      "jsonpath": "$.plugins[?(@.name=='<FIRST>')].source.ref" }
  ]
}
```

`feat:` → minor, `fix:` → patch, `feat!:`/`BREAKING CHANGE` → major. A commit is
attributed to a plugin by the path it touches; keep commits plugin-scoped for
independent bumps.

## Step 5 — Verify

- `jq . .claude-plugin/marketplace.json` parses and has ≥1 `plugins[]` entry.
- Each catalog `name` has a `plugins/<name>/` dir, a manifest entry, and a
  release-please package.
- Run `/plugin-audit plugins/<FIRST>` → zero findings.

## Completion report

```text
Marketplace scaffolded: <OWNER>
Catalog:  .claude-plugin/marketplace.json (1 plugin slot: <FIRST>)
Release:  release-please-config.json + .release-please-manifest.json
Plugin:   plugins/<FIRST>/ (/plugin-audit → zero findings)
Next:     add more plugins with /scaffold-plugin <name>
```
