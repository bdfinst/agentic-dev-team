# agentic-security-assessment — DEPRECATED legacy stub

> **This plugin has been renamed.** The security companion now lives at
> `security-assessment@bfinster`. This stub exists only to migrate
> installs of the old plugin id.

## What this stub does

This is **not** the real plugin. It contains exactly one command —
`/upgrade` — whose job is to install `security-assessment@bfinster` and
then uninstall itself.

## Migrate now

From any Claude Code session with this stub loaded:

```
/upgrade
```

After it finishes, restart Claude Code. You'll have the full security
companion back: the `/security-assessment` pipeline, `/cross-repo-analysis`,
the adversarial-ML red-team harness (`/redteam-model`), FP-reduction,
compliance mapping, and all custom semgrep rulesets.

## Sunset

This stub will be removed from the marketplace catalog no earlier than
**2027-06-01**. Migrate before then.

## Real plugin

→ [`security-assessment@bfinster`](https://github.com/bdfinst/agentic-dev-team/tree/main/plugins/security-assessment)
