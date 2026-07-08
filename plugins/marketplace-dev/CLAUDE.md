# marketplace-dev — build, audit, and maintain Claude Code plugins

`marketplace-dev` gives plugin authors the scaffolding, audit, and self-maintenance
infrastructure the `dev-team` plugin developed internally — as reusable, installable
tooling. It targets three workflows: **creating a new plugin** from scratch,
**improving an existing plugin's** architecture and quality, and **establishing a
new marketplace** with correct structure from the start.

It encodes the conventions in
[`docs/marketplace-builder-plugin-playbook.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/docs/marketplace-builder-plugin-playbook.md)
— directory layout, agent/skill frontmatter contracts, the markdown-vs-script
decision framework, and the eval-fixture pattern — as scaffolding skills, a
structural review agent, and a single shared knowledge file.

`marketplace-dev` has **no hard runtime dependency on `dev-team`**.

## Slash commands

| Command | Role | What it does |
|---|---|---|
| `/scaffold-plugin <name>` | implementation | Create a new plugin dir with the audit-clean skeleton (`plugin.json`, `CLAUDE.md`, `install.sh`, `settings.json`, `agents/ skills/ hooks/ knowledge/`) |
| `/scaffold-marketplace <owner>` | implementation | Create a marketplace root — catalog, release-please wiring, ≥1 plugin slot |
| `/init-plugin-eval <name>` | implementation | Scaffold `evals/<name>/{fixtures,expected}/` + a grading-contract README (empty corpus grades as a clean no-op) |
| `/agent-type-advisor <prose \| file>` | worker | Recommend **markdown** vs **script** for a use-case (forward-looking) or audit an existing agent/skill file (retrospective), with rule citations |
| `/plugin-audit [dir] [--fix]` | orchestrator | Generalized structural compliance for any plugin — agent type, frontmatter, eval coverage, body budgets (architecture only) |
| `/agent-create` | worker | Create an agent file following the official schema and token budgets |
| `/agent-skill-authoring` | worker | Conventions, anti-patterns, and meta-patterns for authoring agents and skills |
| `/agent-add` | implementation | Create a new review or team agent (delegates to `agent-create`) |
| `/agent-remove` | implementation | Remove an agent and clean up its registry/doc references |
| `/add-plugin <name@marketplace>` | implementation | Install a plugin and register it in a project's `settings.json` |

## Agent

- **`plugin-best-practices-review`** — read-only, JSON output, structural findings.
  Checks agent type appropriateness (markdown vs script), frontmatter compliance,
  eval-coverage presence, and body line-count budgets. It does **not** evaluate
  detection-logic quality — that belongs to the plugin's own `agent-eval`.

## Knowledge

- [`knowledge/agent-type-decision-rules.md`](knowledge/agent-type-decision-rules.md)
  — the markdown-vs-script decision matrix (rules R1–R10). The single source of
  truth shared by `/agent-type-advisor` (forward-looking) and
  `plugin-best-practices-review` (retrospective). Cite rule IDs; never restate.

## Conventions enforced

- **Shipping hygiene.** Only shipped files live under `plugins/<name>/`. Eval
  fixtures and tests live at the repo root (`evals/<name>/`, `tests/`) — never
  inside a plugin dir.
- **Independent versioning.** Each plugin carries its own semver in its
  `plugin.json`; release-please keeps `plugin.json`, the release tag, and the
  catalog entry in lock-step. Do not hand-edit versions.
- **Portability.** All shell is `#!/usr/bin/env bash` and bash 3.2-safe across
  macOS, Linux, and Git Bash on Windows; every `install.sh` carries the
  Git-Bash-on-Windows guard.
- **Audit-clean bar.** Scaffolded plugins and migrated skills must pass
  `/plugin-audit` with zero findings; `plugin-best-practices-review` produces zero
  findings against `marketplace-dev` itself (dogfood).

## Documentation

| Doc | Covers |
|---|---|
| [Workflows](docs/workflows.md) | All commands — scaffolding, agent authoring, maintenance |
| [Skills catalog](docs/skills.md) | Full skill/command list with descriptions |
| [Agents](docs/agent_info.md) | `plugin-best-practices-review` agent and dispatch model |
| [Agent-type Decision Rules](knowledge/agent-type-decision-rules.md) | Markdown vs. script decision matrix (R1–R10) |

## Eval fixtures

Live at `evals/marketplace-dev/` in the repo root (not shipped). Run the
structural check with
`python3 scripts/eval_grade.py --check-corpus --expected-dir evals/marketplace-dev/expected --fixtures-dir evals/marketplace-dev/fixtures`.
