# agentic-dev-team — DEPRECATED legacy stub

> **This plugin has been renamed.** The full development team now lives at
> `dev-team@bfinster`. This stub exists only to migrate installs of the
> old plugin id.

## What this stub does

This is **not** the real plugin. It contains exactly one command — `/upgrade` —
whose job is to install `dev-team@bfinster` and then uninstall itself.

If you're seeing this README, you're either:

- **An installed user on a pre-rename version** whose marketplace
  auto-resolved to this stub when `/upgrade` ran — perfect, just run
  `/upgrade` again from this stub and you'll land on the real plugin.
- **A fresh installer who picked the old id by mistake** — uninstall this
  stub and install `dev-team@bfinster` instead.

## Migrate now

From any Claude Code session with this stub loaded:

```
/upgrade
```

That's it. The command installs `dev-team@bfinster`, removes this stub,
and tells you to restart Claude Code. After restart you have the full
team back: orchestrator, software-engineer, qa-engineer, all reviewers,
the four-command workflow (`/specs → /plan → /build → /pr`), and every
skill.

## Sunset

This stub will be removed from the marketplace catalog no earlier than
**2027-06-01**. Migrate before then.

## Real plugin

→ [`dev-team@bfinster`](https://github.com/bdfinst/agentic-dev-team/tree/main/plugins/dev-team)

The repository name on GitHub (`bdfinst/agentic-dev-team`) is unchanged
— only the marketplace plugin id was renamed.
