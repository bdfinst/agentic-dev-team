# Agentic Dev Team — Plugin Development

This is the marketplace repository for the agentic-dev-team Claude Code plugin.

## Repository Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog (points to plugins/)
plugins/agentic-dev-team/          # The plugin source
├── .claude-plugin/plugin.json     # Plugin manifest + version
├── agents/                        # Team agents + review agents
├── commands/                      # Slash command definitions
├── skills/                        # Reusable knowledge modules
├── hooks/                         # PreToolUse and PostToolUse scripts
├── knowledge/                     # Progressive disclosure reference files
├── templates/                     # Language-specific agent templates
├── settings.json                  # Hook registrations (ships with plugin)
├── install.sh                     # Prerequisite checker
└── CLAUDE.md                      # Plugin instructions (ships with plugin)

docs/                              # Dev documentation (not shipped)
plans/                             # Implementation plans (not shipped)
evals/                             # Agent eval fixtures (not shipped)
reports/                           # Review reports (not shipped)
```

## Developing the Plugin

Edit files directly in `plugins/agentic-dev-team/`. All plugin components (agents, skills, commands, hooks) live there.

### Testing locally

Install the plugin from the local path into a test project:

```bash
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-dev-team
```

### Adding agents, skills, or commands

- **Agent**: Add a `.md` file to `plugins/agentic-dev-team/agents/`
- **Skill**: Add a `.md` file to `plugins/agentic-dev-team/skills/`
- **Command**: Add a `.md` file to `plugins/agentic-dev-team/commands/`
- **Hook**: Add a `.sh` script to `plugins/agentic-dev-team/hooks/` and register it in `plugins/agentic-dev-team/settings.json`

After changes, run `/agent-audit` to verify structural compliance.

### Releasing

Releases are managed by release-please. Push conventional commits to main:
- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE` → major version bump

A release PR is opened automatically. Merging it creates a GitHub Release with a version tag.

See `plugins/agentic-dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
