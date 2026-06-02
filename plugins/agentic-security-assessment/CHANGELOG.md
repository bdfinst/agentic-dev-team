# Changelog — agentic-security-assessment (legacy stub)

The real changelog lives at [`plugins/security-assessment/CHANGELOG.md`](../security-assessment/CHANGELOG.md). This file only tracks the deprecation stub.

## [3.0.2] - 2026-06-02

### Added

- SessionStart hook (`hooks/deprecation-banner.sh`) that fires on every Claude Code launch and prints a high-visibility deprecation notice. Same rationale as `agentic-dev-team@6.0.2`.

### Changed

- Updated `commands/upgrade.md` opening prose to address the half-migrated session state.

## [3.0.1] - 2026-06-02

### Changed

- **DEPRECATED**: this plugin id was renamed to `security-assessment@bfinster` in v3.0.0. This release republishes the old name as a deprecation stub whose `/upgrade` command auto-migrates the install to the new id.
- All agents, skills, commands (except `/upgrade`), hooks, knowledge, harness, and prompts removed — they live in `security-assessment@bfinster` now.

### Why

The pre-rename `/upgrade` was shipped only in `agentic-dev-team`, but anyone with both legacy plugins installed needs a path to migrate this one too. After running `/upgrade` from the renamed `dev-team`, this stub catches the second leg of the migration.

### Sunset

Scheduled for removal from the marketplace catalog no earlier than 2027-06-01.

## Pre-deprecation history

See [`plugins/security-assessment/CHANGELOG.md`](../security-assessment/CHANGELOG.md).
