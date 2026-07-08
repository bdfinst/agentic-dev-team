# Skills

All skills in the `marketplace-dev` plugin. Seven are user-invocable slash commands; three are
internal implementation skills used by other skills or agents.

## Command Table

| Command | File | Role | What It Does |
| --- | --- | --- | --- |
| `/plugin-audit` | `skills/plugin-audit/SKILL.md` | orchestrator | Generalized structural compliance for any plugin — agent type, frontmatter, eval coverage, body budgets |
| `/scaffold-plugin` | `skills/scaffold-plugin/SKILL.md` | implementation | Create a new plugin dir with the audit-clean skeleton |
| `/scaffold-marketplace` | `skills/scaffold-marketplace/SKILL.md` | implementation | Create a marketplace root — catalog, release-please wiring, ≥1 plugin slot |
| `/init-plugin-eval` | `skills/init-plugin-eval/SKILL.md` | implementation | Scaffold `evals/<name>/{fixtures,expected}/` + a grading-contract README |
| `/agent-type-advisor` | `skills/agent-type-advisor/SKILL.md` | worker | Recommend markdown vs script for a use-case or audit an existing file |
| `/agent-create` | `skills/agent-create/SKILL.md` | worker | Create an agent file following the official schema and token budgets |
| `/agent-skill-authoring` | `skills/agent-skill-authoring/SKILL.md` | worker | Conventions, anti-patterns, and meta-patterns for authoring agents and skills |
| `/agent-add` | `skills/agent-add/SKILL.md` | implementation | Create a new review or team agent (delegates to `agent-create`) |
| `/agent-remove` | `skills/agent-remove/SKILL.md` | implementation | Remove an agent and clean up its registry/doc references |
| `/add-plugin` | `skills/add-plugin/SKILL.md` | implementation | Install a plugin and register it in a project's `settings.json` |
