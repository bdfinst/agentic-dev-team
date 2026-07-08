# Workflows

The `marketplace-dev` plugin exposes its capabilities as **slash commands** — there are no multi-phase orchestrator workflows. Each command is a self-contained implementation or worker unit.

---

## Plugin scaffolding

### `/scaffold-plugin <name>`

Creates a new plugin directory with the correct, audit-clean structure: `plugin.json`, `CLAUDE.md`, `install.sh`, `settings.json`, and the standard subdirectories (`agents/`, `skills/`, `hooks/`, `knowledge/`). The generated directory passes `/plugin-audit` with zero findings on a clean install.

**Use when:** starting a new plugin inside a marketplace monorepo.

### `/scaffold-marketplace <owner>`

Creates a marketplace root — catalog (`marketplace.json`), release-please wiring, and at least one plugin slot.

**Use when:** establishing a new marketplace monorepo from scratch.

### `/init-plugin-eval <name>`

Scaffolds `evals/<name>/{fixtures,expected}/` and a grading-contract README. An empty corpus grades as a clean no-op, so the scaffold is safe to commit before any fixtures exist.

**Use when:** adding the first review agent to a new or existing plugin.

---

## Agent authoring

### `/agent-create`

Creates new Claude Code sub-agent files following the official schema and token-efficiency budgets. Handles both review agents (JSON output, read-only tools, ≤ 40-line body) and team agents (prose output, action tools, ≤ 75-line body). Validates against `/plugin-audit` before writing. Updates the agent registry and plugin `CLAUDE.md` after success.

### `/agent-add`

Convenience entry point that delegates to `agent-create`. Use when the user wants to add a review agent or team agent persona.

### `/agent-remove`

Removes an agent file, cleans up all registry entries, removes cross-references, and updates documentation. Always confirms before deleting.

### `/agent-skill-authoring`

Conventions, anti-patterns, and meta-patterns for writing skills (and the shared agent/skill philosophy). Use when creating or editing a `SKILL.md` file.

### `/agent-type-advisor <prose | file>`

Recommends **markdown** vs **script** for a use-case (forward-looking) or audits an existing agent/skill file (retrospective). Cites rules R1–R10 from [`knowledge/agent-type-decision-rules.md`](../knowledge/agent-type-decision-rules.md).

---

## Plugin maintenance

### `/plugin-audit [dir] [--fix]`

Generalized structural compliance check for any Claude Code plugin. Audits: agent type appropriateness, frontmatter compliance, eval coverage, and body line-count budgets. Accepts any plugin directory path; not hardcoded to one plugin. Pass `--fix` to apply auto-correctable findings.

### `/add-plugin <name@marketplace>`

Installs a Claude Code plugin and registers it in the project's `settings.json` so the full team can replicate the install.

---

## Summary

| Command | Category | What it does |
| --- | --- | --- |
| `/scaffold-plugin` | Scaffolding | New plugin skeleton |
| `/scaffold-marketplace` | Scaffolding | New marketplace root |
| `/init-plugin-eval` | Scaffolding | Eval fixture scaffold |
| `/agent-create` | Agent authoring | New agent file |
| `/agent-add` | Agent authoring | Add review/team agent |
| `/agent-remove` | Agent authoring | Remove agent + registry |
| `/agent-skill-authoring` | Agent authoring | Conventions reference |
| `/agent-type-advisor` | Agent authoring | Markdown vs. script recommendation |
| `/plugin-audit` | Maintenance | Structural compliance check |
| `/add-plugin` | Maintenance | Install + register a plugin |

See the [Skills catalog](skills.md) for full per-command descriptions and the [Agents page](agent_info.md) for the single review agent this plugin ships.
