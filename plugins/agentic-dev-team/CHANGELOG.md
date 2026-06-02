# Changelog — agentic-dev-team (legacy stub)

The real changelog lives at [`plugins/dev-team/CHANGELOG.md`](../dev-team/CHANGELOG.md). This file only tracks the deprecation stub.

## [6.0.2] - 2026-06-02

### Added

- SessionStart hook (`hooks/deprecation-banner.sh`) that fires on every Claude Code launch and prints a high-visibility deprecation notice naming the destination plugin and the exact restart-then-`/upgrade` flow. Closes a gap where users running the pre-rename `/upgrade` twice without restarting in between would land on this stub, see "already at latest" on the second run, and walk away thinking migration was complete.

### Changed

- Updated `commands/upgrade.md` opening prose to explicitly call out the "if you just got here from running the pre-rename `/upgrade`, restart first" case.

## [6.0.1] - 2026-06-02

### Changed

- **DEPRECATED**: this plugin id was renamed to `dev-team@bfinster` in v6.0.0. This release republishes the old name as a deprecation stub whose `/upgrade` command auto-migrates the install to the new id (install `dev-team@bfinster` first, then uninstall this stub).
- All agents, skills, commands (except `/upgrade`), hooks, knowledge, prompts, and templates removed — they live in `dev-team@bfinster` now.

### Why

The pre-rename `/upgrade` (shipped in v5.6.0 and earlier) calls `claude plugin update agentic-dev-team@bfinster`, which the marketplace catalog no longer serves under that name after the rename. Without this stub, pre-rename users would be stranded with no auto-migration path.

### Sunset

This stub is scheduled for removal from the marketplace catalog no earlier than 2027-06-01. See `plugins/dev-team/docs/decisions/upgrade-step-0-sunset.md` (when present in the dev-team plugin) for the full rename-cleanup timeline.

## Pre-deprecation history

For releases 5.6.0 and earlier under this plugin id, see [`plugins/dev-team/CHANGELOG.md`](../dev-team/CHANGELOG.md) — the file history is preserved there under the new plugin id.
