# Artifact migration guide (upgrading an existing project)

Audience: **operators**. This guide is for anyone upgrading an existing project's `dev-team` plugin
install across the `.claude/`-scoped runtime artifact change (issue #1406, plan
`opt-in-metrics-and-claude-scoped-artifacts.md`). This is not a maintainer doc.
See [`developer-notes.md`](developer-notes.md) for plugin-development docs.

## What changed

Two coordinated changes:

1. **Consent flips from on-by-default to off-by-default.** A single
   user-level config file gates it: `~/.claude/telemetry.json`. `telemetry.jsonl` and
   `artifact-usage.json` move to `~/.claude/metrics/`.
2. **Every other project-scoped runtime artifact directory** (`metrics/`,
   `memory/`, `plans/`) moves under the project's own `.claude/` instead of the
   repo root. The reports domain (`reports/` + `DEV_TEAM_REPORTS/`)
   consolidates into a new top-level `.dev-team-reports/`.

Each pre-existing file falls into exactly one of three treatments below.
**Never assume a file you rely on was auto-migrated. Check which bucket the file is in.**

## 1. One-time move (writers with a real Python touchpoint)

The plugin moves these files, not copies them, from their old bare path into
`.claude/<category>/`. The move happens **the first time the owning hook/script writes (or, for
one case, reads) after upgrade**. The move is per-file, never a directory
sweep. It skips any file that git tracks. A tracked legacy file stays in
place rather than moving silently out from under version control.

| File | Old path | New path |
| --- | --- | --- |
| `cost-metering.jsonl` | `metrics/cost-metering.jsonl` | `.claude/metrics/cost-metering.jsonl` |
| `{date}-task-log.jsonl` | `metrics/{date}-task-log.jsonl` | `.claude/metrics/{date}-task-log.jsonl` |
| `config-changelog.jsonl` | `metrics/config-changelog.jsonl` | `.claude/metrics/config-changelog.jsonl` |
| `pending-review.jsonl` | `metrics/pending-review.jsonl` | `.claude/metrics/pending-review.jsonl` |
| `learning-loop-state.json` | `metrics/learning-loop-state.json` | `.claude/metrics/learning-loop-state.json` |
| boundary-events log | `metrics/boundary-events.jsonl` | `.claude/metrics/boundary-events.jsonl` |
| `/test-improve`'s phase-state tree | `memory/test-improve/<slug>/` | `.claude/memory/test-improve/<slug>/` (directory-migrated file-by-file on the next resume; `refactor-backlog.md` is excluded — see § 2) |

The shared mechanism is `resolve_file()` (single
file) and `migrate_dir()` (whole subtree, one call per invocation, still
file-by-file, never overwrites an existing destination) in `hooks/lib/artifact_paths.py`. Both are fail-open.
A failed move logs one diagnostic line to stderr. The calling operation
proceeds unaffected. The move never blocks or raises.

`verify-log.jsonl` is a deliberate exception. It stays at the bare
`metrics/verify-log.jsonl` and is **not** part of this migration at all. The plugin never moved, gated, or relocated it.

## 2. Documented clean break (agent-instruction-driven writers, no Python write call site)

Agent *instructions* write these files (skill/agent markdown telling
Claude where to `Write`), not a Python hook. No code path can
migrate them. Pre-existing top-level content is therefore **left in place
permanently**. The plugin does not move it. New writes after upgrade go straight to
the new location. Old and new content end up split across two paths
with no automatic reconciliation.

| File / tree | Old path | New path (new writes only) |
| --- | --- | --- |
| `review-value.jsonl` | `metrics/review-value.jsonl` | `.claude/metrics/review-value.jsonl` |
| `build-phase.json` | `memory/build-phase.json` | `.claude/memory/build-phase.json` (read side uses `migrate=False` deliberately — it never moves the legacy file) |
| `refactor-backlog.md` (`/test-improve`) | `memory/test-improve/<slug>/refactor-backlog.md` | `.dev-team-reports/test-improve/<slug>/refactor-backlog.md` (a report, not runtime state — explicitly excluded from `migrate_dir()`'s `.claude/memory/` sweep; see the reports-domain row below) |
| `/test-improve` reports output | `reports/test-improve/<slug>/` | `.dev-team-reports/test-improve/<slug>/` |
| `/test-improve` plan artifacts | `plans/test-improve/` | `.claude/plans/test-improve/` |
| `DEV_TEAM_REPORTS/`-domain writers (`/review-agent`, `/code-review` interactive, `/triage`, `/report-pdf`, `/ship`, `/exploratory-testing`, `/session-review`) | `DEV_TEAM_REPORTS/...` / `reports/...` | `.dev-team-reports/...` |

**Practical consequence:** if a project has an in-flight `/build` session (a
recorded `build-phase.json`) or unresolved review-value/reports content when it
crosses the upgrade boundary, that in-flight state is effectively
orphaned at the old path. `/build`'s phase tracking for that session
behaves as if no phase is recorded. There is no data-loss risk (nothing is
deleted), but the plugin does not pick up the record after the upgrade.

## 3. Dual-read fallback (transition-window self-healing)

Three reader commands tolerate the split between old and new locations
without any manual step:

- **`/cost-report`** and **`/harness-audit`** read `cost-metering.jsonl`,
  `review-value.jsonl`, and `config-changelog.jsonl`. They prefer
  `.claude/metrics/<file>` and fall back to the bare `metrics/<file>` if the
  new path does not exist yet. This self-heals during the transition window.
  No operator action is needed.
- **`/artifact-lifecycle`** reads `artifact-usage.json` exclusively from
  `~/.claude/metrics/artifact-usage.json` (home-scoped). This file was already
  home-scoped as of the telemetry-consent change, so there is no legacy
  project-scoped fallback to read. Any older doc reference to a
  project-scoped path was a documentation bug. The docs now point to the
  one location where the plugin has ever written the file.

## Consent-file migration is manual, not automatic

Suppose a project previously had a `.claude/telemetry.json` (or, before this change,
any project-level telemetry consent setting) with `{"enabled": true}`. **The plugin does not carry that
setting forward.** The plugin now resolves consent exclusively from
`~/.claude/telemetry.json` (home-scoped). `DEV_TEAM_TELEMETRY` also has no
effect any more.

**Action required:** if you want telemetry after upgrading, re-opt-in at the
new location:

```bash
mkdir -p ~/.claude
echo '{"enabled": true}' > ~/.claude/telemetry.json
```

Nothing reads or migrates a project's old consent file automatically. An
un-migrated project defaults to telemetry disabled (fail-open). This is the
deliberate new default posture, not a bug.

## Quick reference: what to check after upgrading

- [ ] If you rely on telemetry, artifact-usage, or cost data: re-opt-in via
      `~/.claude/telemetry.json` (see above). Nothing carries over.
- [ ] If you have an in-flight `/build` session across the upgrade, expect its
      phase-tracking state to reset (§ 2, `build-phase.json`).
- [ ] Old top-level `reports/`, `DEV_TEAM_REPORTS/`, `memory/`, and
      `plans/test-improve/` content stays exactly where it is. Read it from
      the old path, or move it by hand if you want it under the new tree.
- [ ] The upgrade rewrote `.gitignore` rules for these directories to match the new
      paths. If you have local overrides, re-check them against the new
      `.claude/`-scoped and `.dev-team-reports/`-scoped paths.
