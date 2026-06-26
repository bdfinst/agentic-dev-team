---
name: add-plugin
description: >-
  Install a Claude Code plugin and register it in settings.json so the
  full team can replicate the install. Use this whenever adding a new
  plugin to the project — it keeps settings.json in sync with what is
  actually installed.
argument-hint: >-
  <name@marketplace> [--repo <owner/repo>]
user-invocable: true
allowed-tools: Read, Edit, Bash
---

# Add Plugin

Role: implementation. This skill installs a Claude Code plugin and
adds it to `.claude/settings.json` so the project's plugin set is
reproducible.

You have been invoked with the `/add-plugin` skill.

## Implementation constraints

1. **Always update settings.json.** Installing without registering
   defeats the purpose — the whole point is reproducibility.
2. **Derive marketplace from the identifier.** The `name@marketplace`
   format encodes both; never ask the user to repeat information
   already in the argument.
3. **Do not duplicate entries.** Check settings.json before adding;
   if the plugin is already registered, report it and stop.
4. **Be concise.** Report only the outcome — no narration of each step.

## Parse Arguments

Arguments: $ARGUMENTS

Required: plugin identifier (`$0`) in `name@marketplace` format —
e.g. `skill-creator@claude-plugins-official` or `refactoring@refactoring`.

Optional:

- `--repo <owner/repo>`: GitHub repository to register as the
  marketplace source before installing (e.g. `elifiner/refactoring`).
  Required for plugins not on an official marketplace.

## Steps

### 1. Parse arguments

Extract:
- `NAME` — the part before `@` in `$0`
- `MARKETPLACE` — the part after `@` in `$0`
- `REPO` — value of `--repo`, or empty string if not provided

### 2. Check for existing registration

Read `.claude/settings.json`. If `enabledPlugins` already contains
`"<NAME>@<MARKETPLACE>": true`, report:

```
<NAME>@<MARKETPLACE> is already registered in settings.json. Nothing to do.
```

and stop.

### 3. Register marketplace (if --repo provided)

If `REPO` is non-empty, run:

```bash
claude plugin marketplace add <REPO>
```

If this fails, report the error and stop.

### 4. Install the plugin

Run:

```bash
claude plugin install <NAME>@<MARKETPLACE>
```

If this fails, report the error and stop — do not update settings.json
for a plugin that did not install successfully.

### 5. Add to settings.json

Add to the `enabledPlugins` object in `.claude/settings.json`:

```json
"<NAME>@<MARKETPLACE>": true
```

If a `--repo` was provided, also add to `extraKnownMarketplaces`:

```json
"<MARKETPLACE>": {
  "source": {
    "source": "github",
    "repo": "<REPO>"
  }
}
```

### 6. Report

```
Installed:  <NAME>@<MARKETPLACE>
Repo:       <REPO or "official marketplace">
settings.json: updated
```
