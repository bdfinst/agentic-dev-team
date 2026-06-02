# /upgrade Step 0 — sunset tracker

**Created**: 2026-06-02
**Tracked from**: PR for `refactor/rename-plugins`
**Target removal**: when both `dev-team` and `security-assessment` reach v2.0.0, OR 2027-06-01 — whichever comes first.

## What is being tracked

`plugins/dev-team/commands/upgrade.md` Step 0 detects users still installed under the legacy plugin ids (`agentic-dev-team@*`, `agentic-security-assessment@*`) and migrates them in-place by invoking `evals/upgrade-migration/migrate.py`.

## When to remove

The migration block exists for one purpose only: to walk existing users across the rename. Once it is reasonable to assume every installed user has either migrated via `/upgrade`, reinstalled fresh from the marketplace, or stopped using the plugin altogether, the block becomes dead code that complicates the upgrade flow without serving anyone.

Triggering criteria (whichever fires first):

- **Version-based**: both `dev-team` and `security-assessment` have shipped a v2.0.0 release. The semver major bump signals a fresh contract; users at that boundary have necessarily re-engaged with the plugin and would have migrated by then.
- **Time-based**: 2027-06-01 (≈12 months after rename). Anyone who has not run `/upgrade` in 12 months is unlikely to be on a live install.

## What to remove

When the trigger fires:

1. Delete `Step 0` from `plugins/dev-team/commands/upgrade.md` (the heading, the prose, the `python3 evals/upgrade-migration/migrate.py` invocation, the "If a migration occurred, STOP" instructions, and the sunset paragraph).
2. Delete the `evals/upgrade-migration/` directory.
3. Delete the `check_upgrade_step0` block from `scripts/assert-rename.sh` (or delete the script entirely if the rename refactor's invariants are no longer interesting).
4. Delete this file.
5. Land a single commit: `chore(upgrade): retire legacy plugin-id migration (Step 0 sunset)`.

## Why this lives in `docs/decisions/`

This is a forward-dated maintenance task tied to a specific code block. A GitHub issue would also work; the markdown file is preferred here because the trigger condition (a v2.0.0 release) is something a future maintainer will discover from inside the repo rather than from a tracking dashboard.
