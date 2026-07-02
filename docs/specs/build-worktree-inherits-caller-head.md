<!-- spec-version: 8.4.0 -->

# Spec: /build worktree agents inherit caller's HEAD

## Intent Description

When `/build` fans slices out to isolated git worktrees, each worktree
must see the caller's current branch state — including uncommitted
spec/plan work and any in-progress commits that have not yet reached
`origin/<default>`. Today worktrees branch from `origin/<default>` (the
`fresh` policy), so the `docs/specs/<slug>.md` and `plans/<slug>.md`
files a caller just produced with `/specs`/`/plan` are invisible to the
subagents that consume them. Every `/ship` end-to-end run is broken by
this by default; the only reason recent runs succeeded is that
subagents guessed a `git checkout <sha> -- …` workaround.

The mechanism exists in Claude Code: the `worktree.baseRef: "head"`
setting makes worktree isolation branch from the caller's local HEAD
instead of `origin/<default>`. Slice 0's empirical spike
(`docs/spikes/worktree-baseref-head-spike.md`) confirmed that the
setting works — but *only* at project (`.claude/settings.json`) or
user (`~/.claude/settings.json`) scope. Plugin-scope settings and
project-local (`.claude/settings.local.json`) are ignored by
2.1.198's worktree isolation for this key.

Because the plugin cannot ship a silent default that would take effect
for every consumer, the correct posture is **detect and warn loudly** at
`/build` pre-dispatch: if the effective setting is not `head`, print a
warning that names (a) the exact settings file the user should edit,
(b) the exact JSON snippet to paste, and (c) the
`DEV_TEAM_WORKTREE_BASE_FRESH=1` opt-out for users who deliberately
want fresh-from-origin worktrees. `/build` never mutates a settings
file. Users opt in; the plugin surfaces the need loudly.

*Design history.* An earlier draft proposed a stateful force/restore
fallback that would rewrite a scoped settings file for the duration of
a build. Plan review (4 of 5 reviewers) converged on the same failure
mode — the mechanism was unverifiable by its own tests, and a crash
before restore would leak a persistent override — and the mechanism was
dropped in favor of the detect-and-warn design captured above. A
subsequent proposal placed `worktree.baseRef: "head"` in the plugin's
own `settings.json`; Slice 0's spike disproved that at build time
(plugin-scope settings not honored), and the fix collapsed to the
warning-only design in this spec. See
`plans/build-worktree-inherits-caller-head.md`'s "What changed after
Slice 0" and "Plan Review Summary" sections for the full audit trail.

## Architecture Specification

### Components affected

- `plugins/dev-team/scripts/build-worktree-baseref.sh` (new) — detect
  the effective `worktree.baseRef` value across the settings-scope
  ladder. Degrade-never-abort per the `hooks/lib/model-resolve.sh`
  precedent.
- `plugins/dev-team/skills/build/SKILL.md` — orchestrator step that
  dispatches worktree subagents. New pre-dispatch base-ref check that
  runs in the top-level `/build` session (before any subagent
  dispatch), prints a paste-ready warning when the setting is not
  `head`, and continues without mutating anything.
- `plugins/dev-team/scripts/build-wave-reconcile.sh` — merges wave
  slice branches back into the integration branch. Verified (and if
  necessary, adjusted) to carry the caller's WIP commits into the
  reconciled history alongside the slice diffs.
- `plugins/dev-team/agents/orchestrator.md`,
  `plugins/dev-team/knowledge/request-processing-flow.md` — describe
  the `worktree.baseRef` requirement and name the settings scopes that
  work (project + user) vs. those that do not (plugin, project-local),
  citing the spike file as the audit trail.

### Interfaces

- **Setting**: `worktree.baseRef` (Claude Code changelog v2.1.140+).
  Values: `fresh` (branch from `origin/<default>`) or `head` (branch
  from caller's local HEAD). Read by the Agent tool's worktree
  isolation and by `EnterWorktree`. **Settings-scope constraint
  observed in 2.1.198** (spike evidence): only
  `.claude/settings.json` (project) and `~/.claude/settings.json`
  (user) are honored for this key. `.claude/settings.local.json`
  (project-local) and `plugins/<name>/settings.json` (plugin) are
  **not** honored. This is the constraint the plugin's detect-and-warn
  design accepts.
- **Environment**: `DEV_TEAM_WORKTREE_BASE_FRESH=1` silences
  `/build`'s detect-and-warn message when the user has deliberately
  chosen a non-`head` setting.
- **Reconciler CLI**: `build-wave-reconcile.sh --into <integration>
  --base <ref> --test-cmd "<full suite>" <slice-branch>...`
  (unchanged surface; internal behavior may adjust to preserve WIP
  commits from `<integration>`).

### Dependencies

- Claude Code CLI 2.1.140+ (setting exists), verified working at
  2.1.198.
- `jq` (already a hard dev dependency per repo `CLAUDE.md`).
- No new external dependencies.

### Constraints

- **No settings mutation at build time.** `/build`'s pre-dispatch
  check is read-only. Never writes a settings file. With no mutation,
  there is no crash-recovery surface to worry about — the failure
  mode the plan reviewers flagged is structurally absent.
- **No new tool surface.** Reuses the existing `worktree.baseRef`
  setting; no changes to the Agent tool's interface.
- **User opts in.** The plugin cannot silently fix #553 for every
  install because the CLI does not honor plugin-scope settings for
  this key. The warning is the plugin's only mechanism to surface the
  need; users must edit their own settings.
- **Portable shell.** New/changed scripts stay bash-3.2 safe and work
  on macOS, Linux, and Git Bash on Windows (per repo `CLAUDE.md`).

### Data flow

```
user's .claude/settings.json  (worktree.baseRef: "head")
        or ~/.claude/settings.json
        │
caller branch (issue-XXX)
├── docs/specs/<slug>.md   ← committed on issue-XXX
├── plans/<slug>.md        ← committed on issue-XXX
└── /build begins
    ├── detect worktree.baseRef; warn (do not mutate) if not "head"
    │     └── warning names the file + paste-ready JSON + opt-out env
    ├── dispatch wave 1 slices → each worktree branches from caller HEAD
    │     └── worktree sees the spec + plan naturally
    └── build-wave-reconcile.sh merges slice branches back
        └── caller's WIP commits (spec+plan) are already in the ancestry
```

## Acceptance Criteria

1. **Spike evidence exists.** `docs/spikes/worktree-baseref-head-spike.md`
   documents the settings-scope matrix: project + user honored, plugin
   and project-local not honored (in 2.1.198). This is the audit trail
   the design rests on.

2. **`/build` warns loudly on non-`head`.** In a run where the
   effective `worktree.baseRef` resolves to `fresh`, `unset` (key
   absent from every honored file), or `unknown` (detection failed —
   e.g. `jq` unavailable), `/build` prints a warning that includes:
   (a) `.claude/settings.json` or `~/.claude/settings.json` as the
   file to edit, (b) a paste-ready JSON snippet like
   `"worktree": {"baseRef": "head"}`, and (c) the
   `DEV_TEAM_WORKTREE_BASE_FRESH` opt-out. Then it continues —
   never blocks. **`/build` does not mutate any settings file.**
   Verifiable by a bats test that stubs the setting via the
   `BASEREF_SETTINGS_PATHS` env-var seam and asserts the warning
   tokens appear in the build output.

3. **Opt-out silences the warning.** With
   `DEV_TEAM_WORKTREE_BASE_FRESH=1` set, `/build` emits no warning —
   the user's choice is honored. Verifiable by a bats test that sets
   the env var and asserts no warning is emitted.

4. **End-to-end verification (manual).** On a repo whose
   `.claude/settings.json` sets `worktree.baseRef: "head"`, running
   `/build` against a branch with a commit adding
   `docs/specs/e2e-check.md` (unpushed to origin) results in at least
   one subagent's worktree containing `docs/specs/e2e-check.md` at
   dispatch time. Recorded in the PR description. bats cannot dispatch
   an `isolation:"worktree"` agent from a fixture, so this is a
   documented manual gate in Pre-PR Quality Gate.

5. **Reconciler preserves caller's WIP commits.** After
   `build-wave-reconcile.sh` merges all slice branches into the
   integration branch, the history contains the caller's original WIP
   commits (spec+plan) as ancestors of the reconciled tip. Verifiable
   by a hermetic bats test that seeds a repo with a WIP commit on the
   integration branch after slice branches diverged and asserts the
   sha survives reconcile.

6. **Documentation updated.**
   `plugins/dev-team/skills/build/SKILL.md`,
   `plugins/dev-team/agents/orchestrator.md`, and
   `plugins/dev-team/knowledge/request-processing-flow.md` describe
   the `worktree.baseRef=head` requirement, name the settings scopes
   that work vs. those that don't (per the spike), and link to the
   spike file. Verifiable by grep.

7. **No regression.** `scripts/ci-local.sh` remains green.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Where the fix should live | `requires-stakeholder-input` (iter 1) | human | User initially chose "Both (recommend + fallback)": plugin default in settings.json plus a defensive `/build` verify-and-set. Belt-and-suspenders posture. |
| Whether the reconciler needs its own change | `requires-stakeholder-input` | human | User chose "Yes — include in scope": verify `build-wave-reconcile.sh` carries the caller's WIP commits into the reconciled branch; if it does not, fix it. |
| Whether plugin-scope `worktree.baseRef=head` is actually honored | discovered `requires-stakeholder-input` (Slice 0 spike) | human | Slice 0 empirically disproved the assumption baked into the earlier design. Plugin scope is NOT honored. Fix collapsed to detect-and-warn only; the plugin cannot ship a silent default. |
| Escape-hatch env var name | `inferable` | inference | Repo convention prefixes plugin env vars with `DEV_TEAM_` (see `DEV_TEAM_MAX_PARALLEL_BUILDS`, `DEV_TEAM_AUTO_APPROVE`, `DEV_TEAM_REVIEW_VALUE`). `DEV_TEAM_WORKTREE_BASE_FRESH=1` follows that pattern. |
| Whether to touch the Agent tool's interface | `inferable` | inference | Explicit non-goal in issue #553's "Not in scope" section. |
| Whether to fail loudly or silently when the effective setting is wrong | `inferable` | inference | Repo convention is "loud halt, never silent" (see `/build` Step 4 sub-step 4). Detect-and-warn: warn loudly, do not block. This is not an error; it is a corrected default. |
| Behavior when the caller has uncommitted (not-yet-committed) changes | `inferable` | inference | Out of scope. `head` refs a *commit*, not the index/worktree. The caller is expected to commit spec+plan before `/build` runs — already the `/ship` pipeline's convention. |
| Scope split: is this one feature or several | `inferable` | inference | Single feature. Issue #553 explicitly deferred the two orthogonal observations (async output path, plan-waves parser) as separate issues if pursued. |
| `LOW_VALUE` items skipped | (none) | — | No low-value coverage gaps identified during critique. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would agree that "worktree
      subagents must inherit caller HEAD, and the plugin's job is to
      surface the required user setting loudly" is the goal.
- [x] Every behavior/goal maps to an acceptance criterion (spike →
      criterion 1; warning → 2, 3; end-to-end → 4; reconciler → 5;
      documentation → 6; no regression → 7).
- [x] Architecture constrains without over-engineering — read-only
      detect, no settings mutation, no new tool surface.
- [x] Terminology consistent across artifacts (`worktree.baseRef`,
      `head`, `fresh`, `caller's HEAD`, `WIP commits`, `reconciler`,
      `settings-scope constraint`).
- [x] No contradictions between artifacts — spec and plan were both
      revised together after Slice 0's spike.
- [x] Every gap/ambiguity finding is logged — the initial two
      `requires-stakeholder-input` items were resolved by the user,
      and the Slice 0 spike-driven finding is logged as its own row
      with the human's chosen resolution ("drop Slice 1; keep
      detect-and-warn").
