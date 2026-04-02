# Specification: Plugin Directory Restructure

**Created**: 2026-04-02
**Status**: approved

## Intent Description

**What**: Restructure the repository to separate marketplace from plugin. Move all plugin components into `plugins/agentic-dev-team/`, move hook registrations into a plugin-level `settings.json`, split CLAUDE.md into a plugin-facing config (ships with plugin) and a dev-facing config (stays at root). Remove `dev-setup.sh` in favor of `claude plugin install --scope project` from the local path.

**Why**: The repo conflates marketplace and plugin. Dev artifacts ship with the plugin, hooks are in a user config location, and the structure can't host multiple plugins. This follows the recommended marketplace structure and ensures hooks distribute with the plugin.

**Scope**: Directory restructure + hook registration move + CLAUDE.md split. No behavioral changes to any agent, command, skill, or hook.

## User-Facing Behavior

```gherkin
Feature: Plugin directory restructure

  Scenario: Plugin installs from marketplace with correct structure
    Given the marketplace.json source points to ./plugins/agentic-dev-team
    When a user runs claude plugin install agentic-dev-team
    Then the plugin is installed with agents, commands, skills, and hooks
    And hook registrations from the plugin's settings.json are active

  Scenario: Hooks are registered via plugin settings.json
    Given the plugin has a settings.json at plugins/agentic-dev-team/settings.json
    When the plugin is installed
    Then PreToolUse and PostToolUse hooks are active
    And no .claude/settings.json is required for hook registration

  Scenario: Dev artifacts are not shipped with the plugin
    Given docs, plans, evals, and reports directories exist at the marketplace root
    When the plugin is installed from plugins/agentic-dev-team
    Then only plugin components are installed
    And dev artifacts at the marketplace root are not included

  Scenario: Plugin CLAUDE.md ships with plugin
    Given plugins/agentic-dev-team/CLAUDE.md contains the orchestration pipeline config
    When the plugin is installed
    Then users see the pipeline config as project instructions

  Scenario: Dev CLAUDE.md guides plugin development
    Given the root CLAUDE.md contains development instructions
    When a developer works on the marketplace repo
    Then they see instructions for adding agents, testing, and contributing

  Scenario: Local plugin testing without symlinks
    Given a developer wants to test plugin changes locally
    When they run claude plugin install --scope project ./plugins/agentic-dev-team
    Then the plugin is installed from the local path
    And dev-setup.sh is no longer needed

  Scenario: release-please updates the correct files
    Given release-please config points to plugins/agentic-dev-team/.claude-plugin/plugin.json
    When a release PR is created
    Then the version is updated in the plugin's plugin.json
    And the version is updated in .claude-plugin/marketplace.json at the repo root
```

## Architecture Specification

**Components moved** (root → `plugins/agentic-dev-team/`):
- `agents/`, `commands/`, `skills/`, `hooks/`, `knowledge/`, `prompts/`, `templates/`
- `CLAUDE.md` (pipeline config) → `plugins/agentic-dev-team/CLAUDE.md`
- `install.sh` → `plugins/agentic-dev-team/install.sh`
- `.claude-plugin/plugin.json` → `plugins/agentic-dev-team/.claude-plugin/plugin.json`

**Components created**:
- `plugins/agentic-dev-team/settings.json` — hook registrations from `.claude/settings.json`
- Root `CLAUDE.md` — rewritten as dev instructions (based on current `.claude/CLAUDE.md`)

**Components updated at marketplace root**:
- `.claude-plugin/marketplace.json` — source: `"./"` → `"./plugins/agentic-dev-team"`
- `.claude/settings.json` — stripped to `enabledPlugins` only
- `release-please-config.json` — extra-files paths updated
- `README.md` — updated paths and install instructions
- `GETTING-STARTED.md` — updated paths

**Components removed**:
- `dev-setup.sh` — replaced by `claude plugin install --scope project ./plugins/agentic-dev-team`
- `.claude/CLAUDE.md` — content merged into new root `CLAUDE.md`

**Components that stay at marketplace root**:
- `.claude-plugin/marketplace.json`
- `docs/`, `plans/`, `evals/`, `reports/`, `memory/`
- `README.md`, `GETTING-STARTED.md`, `LICENSE`
- `release-please-config.json`, `.release-please-manifest.json`
- `.gitignore`, `.github/`

**release-please extra-files**:
- `plugins/agentic-dev-team/.claude-plugin/plugin.json` (version field)
- `.claude-plugin/marketplace.json` (stays at root, JSONPath `$.plugins[0].version`)

## Acceptance Criteria

- [ ] All plugin components live under `plugins/agentic-dev-team/`
- [ ] `marketplace.json` stays at root, source points to `./plugins/agentic-dev-team`
- [ ] `plugins/agentic-dev-team/settings.json` contains all hook registrations
- [ ] `.claude/settings.json` contains only `enabledPlugins` (no hooks)
- [ ] `plugins/agentic-dev-team/.claude-plugin/plugin.json` exists with correct version
- [ ] `plugins/agentic-dev-team/CLAUDE.md` contains the orchestration pipeline config
- [ ] Root `CLAUDE.md` contains development instructions for the repo
- [ ] `release-please-config.json` extra-files point to new plugin.json path
- [ ] Dev artifacts remain at repo root, not shipped with plugin
- [ ] `dev-setup.sh` is removed
- [ ] `.claude/CLAUDE.md` is removed (content in root CLAUDE.md)
- [ ] `git mv` used for moves to preserve history
- [ ] All internal relative paths within the plugin still resolve
