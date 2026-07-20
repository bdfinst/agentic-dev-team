# marketplace-dev

Plugin-author toolkit for Claude Code. Scaffold new plugins and marketplaces,
audit any plugin for structural compliance, and maintain existing plugins with
confidence.

`marketplace-dev` has **no hard runtime dependency on `dev-team`** — install it
on its own to build or maintain plugins.

## When to use this

- **Starting a new plugin**: the `scaffold-plugin` skill generates an audit-clean
  skeleton in one command.
- **Authoring agents or skills**: `/agent-type-advisor` recommends markdown vs.
  script for a use-case; `/agent-create` generates a correctly structured agent
  file.
- **Auditing an existing plugin**: the `plugin-audit` skill produces a structured
  findings report with zero noise for compliant plugins.
- **Setting up a new marketplace**: the `scaffold-marketplace` skill wires the
  catalog, release-please config, and at least one plugin slot.

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and
  authenticated.
- `jq` — used by structural checks.
  - macOS: `brew install jq`
  - Linux: `apt install jq` or `yum install jq`

**Optional:**

- `git` — used for commit-scoped audit snapshots.

### Install the plugin

```bash
# From the marketplace
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install marketplace-dev@bfinster

# From a local clone
claude plugin install --scope project /path/to/agentic-dev-team/plugins/marketplace-dev
```

## Skills & commands

Six skills are **user-invocable** slash commands; the four scaffolding/audit
skills are **agent-loaded** — Claude dispatches them when the task calls for it
rather than you typing a slash command. The [Skills catalog](docs/skills.md) is
the canonical, generated list with full frontmatter descriptions.

| Skill | Invocation | What it does |
|---|---|---|
| `agent-type-advisor` | `/agent-type-advisor <prose\|file>` | Recommend markdown vs. script for a use-case, or audit an existing file |
| `agent-create` | `/agent-create` | Create an agent file following the official schema and token budgets |
| `agent-skill-authoring` | `/agent-skill-authoring` | Conventions, anti-patterns, and meta-patterns for authoring agents and skills |
| `agent-add` | `/agent-add` | Create a new review or team agent (delegates to `agent-create`) |
| `agent-remove` | `/agent-remove` | Remove an agent and clean up registry/doc references |
| `add-plugin` | `/add-plugin <name@marketplace>` | Install a plugin and register it in a project's `settings.json` |
| `scaffold-plugin` | agent-loaded | Create a new plugin dir with the audit-clean skeleton |
| `scaffold-marketplace` | agent-loaded | Create a marketplace root — catalog, release-please wiring, ≥1 plugin slot |
| `init-plugin-eval` | agent-loaded | Scaffold `evals/<name>/{fixtures,expected}/` + grading-contract README |
| `plugin-audit` | agent-loaded | Structural compliance check — agent type, frontmatter, eval coverage, body budgets |

## Agent

**`plugin-best-practices-review`** — read-only, JSON output, structural findings.
Checks agent type appropriateness (markdown vs. script), frontmatter compliance,
eval-coverage presence, and body line-count budgets. It does **not** evaluate
detection-logic quality — that belongs to the plugin's own `agent-eval`.

## Documentation

| Doc | Covers |
|---|---|
| [Workflows](docs/workflows.md) | All commands — scaffolding, agent authoring, maintenance |
| [Skills catalog](docs/skills.md) | Full skill/command list with descriptions and options |
| [Agents](docs/agent_info.md) | `plugin-best-practices-review` agent and dispatch model |
| [Agent-type Decision Rules](knowledge/agent-type-decision-rules.md) | Markdown vs. script decision matrix (R1–R10) |

## Conventions enforced

- **Shipping hygiene.** Only shipped files live under `plugins/<name>/`. Eval
  fixtures and tests live at the repo root (`evals/<name>/`, `tests/`).
- **Independent versioning.** Each plugin carries its own semver in `plugin.json`;
  release-please keeps `plugin.json`, the release tag, and the catalog entry in
  lock-step. Do not hand-edit versions.
- **Portability.** All shell is `#!/usr/bin/env bash`, bash 3.2-safe across macOS,
  Linux, and Git Bash on Windows; every `install.sh` carries the Git-Bash-on-Windows
  guard.
- **Audit-clean bar.** Scaffolded plugins and migrated skills must pass
  `/plugin-audit` with zero findings; `plugin-best-practices-review` produces zero
  findings against `marketplace-dev` itself (dogfood).
