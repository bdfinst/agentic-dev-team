# marketplace-dev

Build, audit, and maintain Claude Code plugins and marketplaces. `marketplace-dev` gives plugin
authors the scaffolding, audit, and self-maintenance infrastructure the `dev-team` plugin developed
internally — as reusable, installable tooling. It targets three workflows: **creating a new plugin**
from scratch, **improving an existing plugin's** architecture and quality, and **establishing a new
marketplace** with correct structure from the start.

It encodes the conventions in
[`docs/marketplace-builder-plugin-playbook.md`](../../docs/marketplace-builder-plugin-playbook.md)
— directory layout, agent/skill frontmatter contracts, the markdown-vs-script decision framework,
and the eval-fixture pattern — as scaffolding skills, a structural review agent, and a single shared
knowledge file.

`marketplace-dev` has **no hard runtime dependency on `dev-team`**.

## Design

`marketplace-dev` is the self-maintenance plugin for the marketplace monorepo pattern. It encodes
the conventions the `dev-team` plugin developed in its own repo as reusable tooling:

- **Scaffolding** (`/scaffold-plugin`, `/scaffold-marketplace`, `/init-plugin-eval`) — emit the
  correct skeleton so new plugins start audit-clean.
- **Structural audit** (`/plugin-audit` + `plugin-best-practices-review` agent) — catch agent type
  mismatches, frontmatter gaps, missing eval coverage, and body budget violations.
- **Agent authoring** (`/agent-create`, `/agent-add`, `/agent-remove`, `/agent-skill-authoring`,
  `/agent-type-advisor`) — create and maintain agents following the official schema.
- **Marketplace self-maintenance** (`/add-plugin`) — install plugins from any marketplace and wire
  them into a project's `settings.json`.

Detection-logic quality evaluation is explicitly out of scope here — it belongs to each plugin's
own `agent-eval`. This plugin audits structure, not semantics.

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated.
- `jq` — JSON parsing in hooks.
  - macOS: `brew install jq`
  - Linux: `apt install jq`

**Optional:**

- `git` — used by `/scaffold-plugin` and `/scaffold-marketplace` to initialize the new plugin or
  marketplace as a git repository.

### Install from GitHub (recommended)

```bash
claude plugin marketplace add bdfinst/agentic-dev-team
claude plugin install marketplace-dev@bfinster
```

### Upgrading

```bash
claude plugin update --scope <scope> marketplace-dev@bfinster
```

Or run `/upgrade` from any session.

### Verify

After installing, confirm the plugin loaded:

```
> /plugin-audit
```

## What's included

- **1 review agent** — `plugin-best-practices-review` (structural findings only; JSON output)
- **10 skills** — 7 user-invocable slash commands plus 3 internal implementation skills
- **1 knowledge file** — `knowledge/agent-type-decision-rules.md` (rules R1–R10)

Full catalogs:
[Agents](docs/agent_info.md) ·
[Skills](docs/skills.md) ·
[Workflows](docs/workflows.md)

## Conventions enforced

- **Shipping hygiene.** Only shipped files live under `plugins/<name>/`. Eval fixtures and tests
  live at the repo root (`evals/<name>/`, `tests/`) — never inside a plugin dir.
- **Independent versioning.** Each plugin carries its own semver in its `plugin.json`;
  release-please keeps `plugin.json`, the release tag, and the catalog entry in lock-step.
- **Portability.** All shell is `#!/usr/bin/env bash` and bash 3.2-safe across macOS, Linux,
  and Git Bash on Windows.
- **Audit-clean bar.** Scaffolded plugins and migrated skills must pass `/plugin-audit` with
  zero findings; `plugin-best-practices-review` produces zero findings against `marketplace-dev`
  itself (dogfood).

## Eval fixtures

Live at `evals/marketplace-dev/` in the repo root (not shipped). Run the structural check with:

```bash
python3 scripts/eval_grade.py \
  --check-corpus \
  --expected-dir evals/marketplace-dev/expected \
  --fixtures-dir evals/marketplace-dev/fixtures
```
