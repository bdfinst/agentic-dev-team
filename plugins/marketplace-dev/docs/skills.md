# Skills

<!-- GENERATED FILE — do not edit by hand.
     Rows: each plugins/marketplace-dev/skills/<name>/SKILL.md (and plugins/marketplace-dev/commands/<name>.md if present).
     Grouping: plugins/marketplace-dev/skill_categories.yaml (by capability).
     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py --plugin-dir plugins/marketplace-dev
     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->

Skills are the unified reusable capability layer in this plugin. Skills live in `skills/<name>/SKILL.md`; user-invocable commands live in `commands/<name>.md`. This catalog groups them **by capability** (the sections below); each row's description is the file's own frontmatter `description`, verbatim.

Most skills are **user-invocable** as slash commands — shown as `/name`; run them directly or let the Orchestrator dispatch them. The rest are **agent-loaded** knowledge modules — shown as a plain `name` — that agents read for domain expertise.


## Plugin Scaffolding

| Skill | File | Description |
| --- | --- | --- |
| init-plugin-eval | [`init-plugin-eval/SKILL.md`](../skills/init-plugin-eval/SKILL.md) | Scaffold the eval directory structure for a plugin's review agents and advisory skills. Use after creating a plugin or adding its first review agent, or when the user says "set up evals for this plugin", "init plugin evals", "scaffold eval fixtures", or "create the eval harness for <plugin>". Creates the fixtures/ and expected/ dirs plus a README describing the grading contract. |
| scaffold-marketplace | [`scaffold-marketplace/SKILL.md`](../skills/scaffold-marketplace/SKILL.md) | Create a Claude Code plugin-marketplace root with a valid catalog, release automation, and at least one plugin slot. Use when starting a new marketplace monorepo, or when the user says "scaffold a marketplace", "set up a plugin marketplace", "create a marketplace catalog", or "bootstrap a marketplace repo". |
| scaffold-plugin | [`scaffold-plugin/SKILL.md`](../skills/scaffold-plugin/SKILL.md) | Create a new Claude Code plugin directory with the correct, audit-clean structure. Use when starting a new plugin in a marketplace monorepo, or when the user says "scaffold a plugin", "create a new plugin", "add a plugin to this marketplace", or "new plugin skeleton". Produces a directory that passes /plugin-audit with zero findings on a clean install. |


## Agent Authoring

| Skill | File | Description |
| --- | --- | --- |
| `/agent-add` | [`agent-add/SKILL.md`](../skills/agent-add/SKILL.md) | Create a new Claude Code agent file (review or team type) following the official sub-agent schema and token-efficiency budgets. Use when the user wants to add a new review agent, detect a new category of code issue, create a team agent persona, or says things like "add an agent for X", "create a reviewer for Y", "new team agent for Z". Also use when given a URL to a coding standard that should become a review agent. |
| `/agent-create` | [`agent-create/SKILL.md`](../skills/agent-create/SKILL.md) | Create new Claude Code sub-agent files following the official schema and token-efficiency budgets. Handles both review agents (JSON output, read-only tools, ≤ 40-line body) and team agents (prose output, action tools, ≤ 75-line body). Use when the user says "add an agent", "create a reviewer for X", "new team agent for Y", or when /agent-add is invoked. Validates against /plugin-audit before writing. Updates the agent registry and plugin CLAUDE.md after success. |
| `/agent-remove` | [`agent-remove/SKILL.md`](../skills/agent-remove/SKILL.md) | Remove an agent from the system — deletes the agent file, cleans up all registry entries, removes cross-references, and updates documentation. Use when the user says "remove the X agent", "delete X-review", "retire the X role", or "we no longer need X". Handles both team agents and review agents. Always confirms before deleting. |
| `/agent-skill-authoring` | [`agent-skill-authoring/SKILL.md`](../skills/agent-skill-authoring/SKILL.md) | Conventions, anti-patterns, and meta-patterns for writing skills (and the shared agent/skill philosophy). Use when creating or editing a SKILL.md file, or when reviewing the agent-vs-skill separation. For the procedural workflow that generates a new agent file, use the agent-create skill (invoked by /agent-add). |
| `/agent-type-advisor` | [`agent-type-advisor/SKILL.md`](../skills/agent-type-advisor/SKILL.md) | Recommend whether a plugin capability should be a markdown (LLM-interpreted) unit or a deterministic script. Use when designing a new agent/skill ("should this be markdown or a script?"), or when auditing an existing agent/skill file for a type mismatch. Accepts either a prose use-case description (forward- looking, new unit) or a path to an existing agent/skill file (retrospective). |


## Plugin Maintenance

| Skill | File | Description |
| --- | --- | --- |
| `/add-plugin` | [`add-plugin/SKILL.md`](../skills/add-plugin/SKILL.md) | Install a Claude Code plugin and register it in settings.json so the full team can replicate the install. Use this whenever adding a new plugin to the project — it keeps settings.json in sync with what is actually installed. |
| plugin-audit | [`plugin-audit/SKILL.md`](../skills/plugin-audit/SKILL.md) | Generalized structural compliance check for any Claude Code plugin. Audits architectural decisions only — agent type appropriateness (markdown vs script), frontmatter compliance, eval coverage, and body line-count budgets. Use when adding or modifying any agent or skill in a plugin, after scaffolding a new plugin, before a migration PR lands, or for a periodic health check. Accepts any plugin directory path; not hardcoded to one plugin's internal structure. |
