# Plan: Plugin Directory Restructure

**Created**: 2026-04-02
**Branch**: main
**Status**: approved
**Spec**: [docs/specs/plugin-restructure.md](../docs/specs/plugin-restructure.md)

## Goal

Separate the marketplace root from the plugin directory by moving all plugin components into `plugins/agentic-dev-team/`. Move hook registrations into the plugin's own `settings.json`. Split CLAUDE.md into plugin-facing (ships) and dev-facing (stays). Remove `dev-setup.sh`.

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

## Steps

### Step 1: Create plugin directory and move components with git mv

**Complexity**: standard
**RED**: N/A — structural move, verified by checking all files exist at new paths
**GREEN**: 
  1. `mkdir -p plugins/agentic-dev-team/.claude-plugin`
  2. `git mv agents/ plugins/agentic-dev-team/agents/`
  3. `git mv commands/ plugins/agentic-dev-team/commands/`
  4. `git mv skills/ plugins/agentic-dev-team/skills/`
  5. `git mv hooks/ plugins/agentic-dev-team/hooks/`
  6. `git mv knowledge/ plugins/agentic-dev-team/knowledge/`
  7. `git mv prompts/ plugins/agentic-dev-team/prompts/`
  8. `git mv templates/ plugins/agentic-dev-team/templates/`
  9. `git mv install.sh plugins/agentic-dev-team/install.sh`
  10. `git mv .claude-plugin/plugin.json plugins/agentic-dev-team/.claude-plugin/plugin.json`
**REFACTOR**: None needed
**Files**: All directories listed above
**Commit**: `refactor: move plugin components into plugins/agentic-dev-team/`

### Step 2: Move CLAUDE.md into plugin, rewrite root CLAUDE.md for dev

**Complexity**: standard
**RED**: N/A — documentation restructure
**GREEN**:
  1. `git mv CLAUDE.md plugins/agentic-dev-team/CLAUDE.md` (pipeline config ships with plugin)
  2. Create new root `CLAUDE.md` with dev-focused content: repo structure, how to add agents/skills, testing instructions (`claude plugin install --scope project ./plugins/agentic-dev-team`), contribution guidelines
  3. Remove `.claude/CLAUDE.md` (its content folded into new root CLAUDE.md)
**REFACTOR**: None needed
**Files**: `CLAUDE.md`, `plugins/agentic-dev-team/CLAUDE.md`, `.claude/CLAUDE.md`
**Commit**: `refactor: split CLAUDE.md into plugin config and dev instructions`

### Step 3: Create plugin settings.json, strip .claude/settings.json

**Complexity**: standard
**RED**: N/A — config move
**GREEN**:
  1. Create `plugins/agentic-dev-team/settings.json` with the full `hooks` object (PreToolUse + PostToolUse) from current `.claude/settings.json`
  2. Strip `.claude/settings.json` to only `enabledPlugins`
**REFACTOR**: None needed
**Files**: `plugins/agentic-dev-team/settings.json` (create), `.claude/settings.json` (edit)
**Commit**: `refactor: move hook registrations to plugin settings.json`

### Step 4: Update marketplace.json source path

**Complexity**: trivial
**RED**: N/A — config update
**GREEN**: Change `.claude-plugin/marketplace.json` source from `"./"` to `"./plugins/agentic-dev-team"`
**REFACTOR**: None needed
**Files**: `.claude-plugin/marketplace.json`
**Commit**: `refactor: point marketplace.json source to plugins/agentic-dev-team`

### Step 5: Update release-please config for new paths

**Complexity**: trivial
**RED**: N/A — config update
**GREEN**: Update `release-please-config.json` extra-files:
  - `.claude-plugin/plugin.json` → `plugins/agentic-dev-team/.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json` stays unchanged (it's at the repo root)
**REFACTOR**: None needed
**Files**: `release-please-config.json`
**Commit**: `ci: update release-please paths for plugin directory restructure`

### Step 6: Remove dev-setup.sh and update .gitignore

**Complexity**: trivial
**RED**: N/A — cleanup
**GREEN**:
  1. `git rm dev-setup.sh`
  2. Update `.gitignore` — remove the `.claude/agents`, `.claude/commands`, `.claude/skills`, `.claude/hooks` symlink entries (no longer needed)
**REFACTOR**: None needed
**Files**: `dev-setup.sh` (delete), `.gitignore`
**Commit**: `chore: remove dev-setup.sh and stale gitignore entries`

### Step 7: Update README.md and GETTING-STARTED.md paths

**Complexity**: standard
**RED**: N/A — documentation
**GREEN**: Update all path references and install instructions in both files to reflect the new structure. Update the local testing instructions to use `claude plugin install --scope project ./plugins/agentic-dev-team`.
**REFACTOR**: None needed
**Files**: `README.md`, `GETTING-STARTED.md`
**Commit**: `docs: update paths for plugin directory restructure`

### Step 8: Verify internal relative paths resolve

**Complexity**: trivial
**RED**: Grep for relative path references (`../skills/`, `../agents/`, `../commands/`, `../knowledge/`) in all moved files and verify they still resolve to existing files
**GREEN**: Fix any broken references (should be none since the tree moved intact)
**REFACTOR**: None needed
**Files**: Any files with broken references
**Commit**: `fix: resolve any broken relative paths` (only if needed)

## Pre-PR Quality Gate

- [ ] All files exist at their new paths
- [ ] No broken relative path references within the plugin
- [ ] `marketplace.json` source points to the correct directory
- [ ] `release-please-config.json` extra-files paths are correct
- [ ] Plugin `settings.json` has all hook registrations
- [ ] `.claude/settings.json` has no hook registrations
- [ ] `/code-review --changed` passes
- [ ] Documentation updated

## Risks & Open Questions

- **Risk**: `git mv` of many directories in one commit may make the diff hard to review. **Mitigation**: Do the structural move in step 1 with no content changes, then config changes in subsequent commits. Reviewers can verify step 1 is a pure move.
- **Risk**: release-please may not find the new plugin.json path on the first run after merge. **Mitigation**: The manifest file (`.release-please-manifest.json`) tracks the version by package path (`.`), not by file path. The extra-files config is what tells it where to write — updating that is sufficient.
- **Risk**: Existing installations via the old marketplace source will break on next `claude plugin update`. **Mitigation**: This is expected for a restructure — users re-install once. Document in the release notes.
