# Artifact migration guide (upgrading an existing project)

Audience: **operators** — anyone upgrading an existing project's `dev-team` plugin
install across the `.claude/`-scoped runtime artifact change (issue #1406, plan
`opt-in-metrics-and-claude-scoped-artifacts.md`). This is not a maintainer doc —
see [`developer-notes.md`](developer-notes.md) for plugin-development docs.

## What changed

Two coordinated changes:

1. **Consent flips from on-by-default to off-by-default**, gated by a single
   user-level config file: `~/.claude/telemetry.json`. `telemetry.jsonl` and
   `artifact-usage.json` move to `~/.claude/metrics/`.
2. **Every other project-scoped runtime artifact directory** (`metrics/`,
   `memory/`, `plans/`) moves under the project's own `.claude/` instead of the
   repo root, and the reports domain (`reports/` + `DEV_TEAM_REPORTS/`)
   consolidates into a new top-level `.dev-team-reports/`.

Each pre-existing file falls into exactly one of three treatments below —
**never assume a file you rely on was auto-migrated; check which bucket it's in.**

## 1. One-time move (writers with a real Python touchpoint)

These files are moved — not copied — from their old bare path into
`.claude/<category>/` **the first time their owning hook/script writes (or, for
one case, reads) after upgrade**. The move is per-file, never a directory
sweep, and skips any file that is git-tracked (a tracked legacy file is left in
place rather than silently moved out from under version control).

| File | Old path | New path |
| --- | --- | --- |
| `cost-metering.jsonl` | `metrics/cost-metering.jsonl` | `.claude/metrics/cost-metering.jsonl` |
| `{date}-task-log.jsonl` | `metrics/{date}-task-log.jsonl` | `.claude/metrics/{date}-task-log.jsonl` |
| `config-changelog.jsonl` | `metrics/config-changelog.jsonl` | `.claude/metrics/config-changelog.jsonl` |
| `pending-review.jsonl` | `metrics/pending-review.jsonl` | `.claude/metrics/pending-review.jsonl` |
| `learning-loop-state.json` | `metrics/learning-loop-state.json` | `.claude/metrics/learning-loop-state.json` |
| boundary-events log | `metrics/boundary-events.jsonl` | `.claude/metrics/boundary-events.jsonl` |
| `/test-improve`'s phase-state tree | `memory/test-improve/<slug>/` | `.claude/memory/test-improve/<slug>/` (directory-migrated file-by-file on the next resume; `refactor-backlog.md` is excluded — see § 2) |

The shared mechanism is `hooks/lib/artifact_paths.py`'s `resolve_file()` (single
file) and `migrate_dir()` (whole subtree, one call per invocation, still
file-by-file — never overwrites an existing destination). Both are fail-open:
a failed move logs one diagnostic line to stderr and the calling operation
proceeds unaffected — it never blocks or raises.

`verify-log.jsonl` is a deliberate exception: it stays at the bare
`metrics/verify-log.jsonl` and is **not** part of this migration at all (it
was never moved, gated, or relocated).

## 2. Documented clean break (agent-instruction-driven writers, no Python write call site)

These files are written by agent *instructions* (skill/agent markdown telling
Claude where to `Write`), not by a Python hook. There is no code path that can
migrate them, so pre-existing top-level content is **left in place
permanently** — it is not moved, and new writes after upgrade go straight to
the new location, meaning old and new content end up split across two paths
with no automatic reconciliation.

| File / tree | Old path | New path (new writes only) |
| --- | --- | --- |
| `review-value.jsonl` | `metrics/review-value.jsonl` | `.claude/metrics/review-value.jsonl` |
| `build-phase.json` | `memory/build-phase.json` | `.claude/memory/build-phase.json` (read side uses `migrate=False` deliberately — it never moves the legacy file) |
| `refactor-backlog.md` (`/test-improve`) | `memory/test-improve/<slug>/refactor-backlog.md` | `.dev-team-reports/test-improve/<slug>/refactor-backlog.md` (a report, not runtime state — explicitly excluded from `migrate_dir()`'s `.claude/memory/` sweep; see the reports-domain row below) |
| `/test-improve` reports output | `reports/test-improve/<slug>/` | `.dev-team-reports/test-improve/<slug>/` |
| `/test-improve` plan artifacts | `plans/test-improve/` | `.claude/plans/test-improve/` |
| `DEV_TEAM_REPORTS/`-domain writers (`/review-agent`, `/code-review` interactive, `/triage`, `/report-pdf`, `/ship`, `/exploratory-testing`) | `DEV_TEAM_REPORTS/...` / `reports/...` | `.dev-team-reports/...` |

**Practical consequence:** if a project has an in-flight `/build` session (a
recorded `build-phase.json`) or unresolved review-value/reports content at the
moment it crosses the upgrade boundary, that in-flight state is effectively
orphaned at the old path — `/build`'s phase tracking for that session will
behave as if no phase is recorded. There is no data-loss risk (nothing is
deleted), but the record will not be picked up post-upgrade.

## 3. Dual-read fallback (transition-window self-healing)

Three reader commands tolerate the split between old and new locations
without any manual step:

- **`/cost-report`** and **`/harness-audit`** read `cost-metering.jsonl`,
  `review-value.jsonl`, and `config-changelog.jsonl` by preferring
  `.claude/metrics/<file>`, falling back to the bare `metrics/<file>` if the
  new path doesn't exist yet. This self-heals during the transition window —
  no operator action needed.
- **`/artifact-lifecycle`** reads `artifact-usage.json` exclusively from
  `~/.claude/metrics/artifact-usage.json` (home-scoped). This file was already
  home-scoped as of the telemetry-consent change, so there is no legacy
  project-scoped fallback to read — any older doc reference to a
  project-scoped path was a documentation bug, now corrected to point at the
  one location the file has ever actually been written to.

## Consent-file migration is manual — not automatic

If a project previously had a `.claude/telemetry.json` (or, pre-this-change,
any project-level telemetry consent setting) with `{"enabled": true}`, **that
setting is not carried forward.** Consent is now resolved exclusively from
`~/.claude/telemetry.json` (home-scoped). `DEV_TEAM_TELEMETRY` also has no
effect any more.

**Action required:** if you want telemetry after upgrading, re-opt-in at the
new location:

```bash
mkdir -p ~/.claude
echo '{"enabled": true}' > ~/.claude/telemetry.json
```

Nothing reads or migrates a project's old consent file automatically — an
un-migrated project simply defaults to telemetry disabled (fail-open), which
is the deliberate new default posture, not a bug.

## Quick reference: what to check after upgrading

- [ ] If you rely on telemetry, artifact-usage, or cost data: re-opt-in via
      `~/.claude/telemetry.json` (see above) — nothing carries over.
- [ ] If you have an in-flight `/build` session across the upgrade: expect its
      phase-tracking state to reset (§ 2, `build-phase.json`).
- [ ] Old top-level `reports/`, `DEV_TEAM_REPORTS/`, `memory/`,
      `plans/test-improve/` content stays exactly where it is — read it from
      the old path, or move it by hand if you want it under the new tree.
- [ ] `.gitignore` rules for these directories were rewritten to match the new
      paths; if you have local overrides, re-check them against the new
      `.claude/`-scoped and `.dev-team-reports/`-scoped paths.
