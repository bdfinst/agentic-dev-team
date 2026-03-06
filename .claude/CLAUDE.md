# Agentic Dev Team — Local Development

This is the plugin repository for the agentic-dev-team Claude Code plugin.

Agent, skill, command, and hook source files live at the **project root** (not in `.claude/`):

- `agents/` — team agents and review agents
- `skills/` — reusable knowledge modules
- `commands/` — slash command definitions
- `hooks/` — PreToolUse and PostToolUse hook scripts

See @CLAUDE.md for the full orchestration pipeline configuration.

## Developing the Plugin

When modifying agents, skills, or commands in this repo, edit the root-level source files directly. To test changes in a real project, install the plugin into a test project:

```bash
claude plugin install --scope project agentic-dev-team@<your-marketplace>
```

Or run `./dev-setup.sh` to symlink root-level files into `.claude/` for in-repo testing.
