# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## Repository Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog (points to plugins/)
plugins/dev-team/          # The plugin source
├── .claude-plugin/plugin.json     # Plugin manifest + version
├── agents/                        # Team agents + review agents
├── commands/                      # Slash command definitions
├── skills/                        # Reusable knowledge modules
├── hooks/                         # PreToolUse and PostToolUse scripts
├── knowledge/                     # Progressive disclosure reference files
├── templates/                     # Language-specific agent templates
├── docs/                          # Plugin-specific docs (architecture, agents, skills, eval system)
├── settings.json                  # Hook registrations (ships with plugin)
├── install.sh                     # Prerequisite checker
└── CLAUDE.md                      # Plugin instructions (ships with plugin)

docs/                              # Cross-plugin dev documentation (roadmaps, spikes, repo-level specs)
plans/                             # Implementation plans (not shipped)
evals/                             # Agent eval fixtures (not shipped)
reports/                           # Review reports (not shipped)
```

## Developing the Plugin

Edit files directly in `plugins/dev-team/`. All plugin components (agents, skills, commands, hooks) live there.

### Testing locally

Install the plugin from the local path into a test project:

```bash
claude plugin install --scope project /path/to/dev-team/plugins/dev-team
# Or from the marketplace:
# claude plugin install dev-team@bfinster
```

### Adding agents, skills, or commands

- **Agent**: Add a `.md` file to `plugins/dev-team/agents/`
- **Skill**: Add a `.md` file to `plugins/dev-team/skills/`
- **Command**: Add a `.md` file to `plugins/dev-team/commands/`
- **Hook**: Add a `.sh` script to `plugins/dev-team/hooks/` and register it in `plugins/dev-team/settings.json`

After changes, run `/agent-audit` to verify structural compliance.

### Releasing

Releases are managed by release-please. Push conventional commits to main:
- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE` → major version bump

A release PR is opened automatically. Merging it creates a GitHub Release with a version tag.

See `plugins/dev-team/CLAUDE.md` for the full orchestration pipeline configuration.
