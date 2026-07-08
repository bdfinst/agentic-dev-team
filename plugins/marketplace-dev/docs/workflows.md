# Workflows

This page covers every user-invocable command in the marketplace-dev plugin, sourced from
`skills/`. Commands are classified per the top-level/standalone definition:

- **Top-level (multi-agent)** — dispatches Agent tool calls.
- **Standalone (single-purpose)** — implementation or worker; no Agent tool dispatch.

---

## Top-Level Commands

### `/plugin-audit`

**File:** `skills/plugin-audit/SKILL.md`
**Role:** orchestrator

Generalized structural compliance audit for any Claude Code plugin — checks agent type
appropriateness (markdown vs script), frontmatter compliance, eval-coverage presence, and
body line-count budgets. Dispatches `plugin-best-practices-review`. Does not evaluate
detection-logic quality; use the plugin's own `agent-eval` for that.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `[plugin-dir]` | Positional. Path to the plugin directory to audit. Defaults to the current directory. |
| `--fix` | Attempt to auto-fix structural findings where possible. |

---

## Standalone Commands

### `/scaffold-plugin`

**File:** `skills/scaffold-plugin/SKILL.md`
**Role:** implementation

Create a new plugin directory with the audit-clean skeleton: `plugin.json`, `CLAUDE.md`,
`install.sh`, `settings.json`, and empty `agents/`, `skills/`, `hooks/`, `knowledge/` directories.
The scaffold passes `/plugin-audit` with zero findings out of the box.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<plugin-name>` | Positional. Name of the new plugin (required). |
| `--dir plugins/<plugin-name>` | Output directory. Defaults to `plugins/<plugin-name>` relative to the current working directory. |
| `--description "..."` | Short description written into the plugin's `plugin.json`. |

---

### `/scaffold-marketplace`

**File:** `skills/scaffold-marketplace/SKILL.md`
**Role:** implementation

Create a marketplace root with a catalog, release-please wiring, and at least one plugin slot.
Targets developers creating a new `agentic-dev-team`-style monorepo from scratch.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<owner-handle>` | Positional. The marketplace owner handle written into `marketplace.json` (required). |
| `--first-plugin <name>` | Also scaffold a first plugin under `plugins/<name>/`. |

---

### `/init-plugin-eval`

**File:** `skills/init-plugin-eval/SKILL.md`
**Role:** implementation

Scaffold `evals/<plugin-name>/{fixtures,expected}/` and a grading-contract README for a plugin.
An empty corpus grades as a clean no-op, so scaffolding is safe to run before any eval fixtures
exist.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<plugin-name>` | Positional. Name of the plugin to scaffold evals for (required). |
| `--dir evals/<plugin-name>` | Output directory. Defaults to `evals/<plugin-name>`. |

---

### `/agent-type-advisor`

**File:** `skills/agent-type-advisor/SKILL.md`
**Role:** worker

Recommend **markdown** vs **script** for a use-case (forward-looking) or audit an existing
agent/skill file (retrospective). Citations reference rules R1–R10 in
`knowledge/agent-type-decision-rules.md`.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<prose use-case \| path/to/agent-or-skill.md>` | Positional. Either a prose description of a new use-case or a path to an existing agent/skill file (required). |

---

### `/agent-create`

**File:** `skills/agent-create/SKILL.md`
**Role:** worker

Create an agent file following the official schema and token budgets. Validates the output
against the schema before writing.

**Flags:** none. Accepts a free-form description of the agent's purpose and scope.

---

### `/agent-skill-authoring`

**File:** `skills/agent-skill-authoring/SKILL.md`
**Role:** worker

Conventions, anti-patterns, and meta-patterns for authoring agents and skills. Use when starting
a new agent or skill to get the philosophy, token-budget rules, and schema contracts up front.

**Flags:** none. Reference/advisory; no arguments.

---

### `/agent-add`

**File:** `skills/agent-add/SKILL.md`
**Role:** implementation

Create a new review or team agent by delegating to `/agent-create`, then register it in the
plugin's catalog and update relevant documentation references.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<description-or-url>` | Positional. Free-form description of the agent or a URL to its source spec (required). |
| `--plugin <dir>` | Plugin directory to add the agent into. Defaults to the current plugin. |
| `--name <name>` | Agent name (file basename). Derived from description if omitted. |
| `--type review\|team` | Agent category. |
| `--effort low\|medium\|high` | Effort band written into the agent's `effort:` frontmatter. |
| `--context diff-only\|full-file\|project-structure` | Context scope for the agent. |
| `--lang <exts>` | Comma-separated file extensions this agent specializes in. |
| `--dry` | Print what would be created without writing files. |

---

### `/agent-remove`

**File:** `skills/agent-remove/SKILL.md`
**Role:** implementation

Remove an agent and clean up its references in the plugin's registry, documentation, and any
skill files that mention it.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<agent-name>` | Positional. Name of the agent to remove (required). |
| `--plugin <dir>` | Plugin directory containing the agent. Defaults to the current plugin. |
| `--dry` | Print what would be removed without modifying files. |

---

### `/add-plugin`

**File:** `skills/add-plugin/SKILL.md`
**Role:** implementation

Install a Claude Code plugin from a marketplace and register it in the project's `settings.json`.

**Flags:**

| Flag | Behavior |
| --- | --- |
| `<name@marketplace>` | Positional. Plugin name and marketplace, e.g. `dev-team@bfinster` (required). |
| `--repo <owner/repo>` | Override the marketplace's default repository source. |
