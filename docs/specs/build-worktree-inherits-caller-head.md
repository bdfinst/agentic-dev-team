<!-- spec-version: 8.4.0 -->

# Spec: /build worktree agents inherit caller's HEAD

## Intent Description

When `/build` fans slices out to isolated git worktrees, each worktree must see
the caller's current branch state — including uncommitted spec/plan work and any
in-progress commits that have not yet reached `origin/<default>`. Today
worktrees branch from `origin/<default>` (the `fresh` policy), so the
`docs/specs/<slug>.md` and `plans/<slug>.md` files a caller just produced with
`/specs`/`/plan` are invisible to the subagents that consume them. Every
`/ship` end-to-end run is broken by this by default; the only reason recent
runs succeeded is that subagents guessed a `git checkout <sha> -- …`
workaround.

The change makes the `/ship` pipeline correct by construction: a slice worktree
starts from the caller's HEAD, so the spec, plan, and any prior-wave commits
are already tracked in the worktree's history — no workaround needed, and the
reconciler's merge naturally carries those commits back into the integration
branch.

Two layers, defense in depth:

1. **Plugin default.** `plugins/dev-team/settings.json` sets
   `worktree.baseRef: "head"` so every worktree the plugin spawns inherits the
   caller's HEAD by default.
2. **`/build` detect-and-warn.** Before dispatching worktree subagents,
   `/build` resolves the effective `worktree.baseRef` and, if it is not
   `head` (or if detection cannot be performed), prints a loud warning
   naming the user-visible fix and the opt-out env var. `/build` never
   mutates a settings file — the user's own setting wins. This surfaces
   a user-level override of the plugin default loudly instead of silently
   reintroducing the bug.

*Design note.* An earlier draft of this spec proposed a stateful
force/restore fallback that would rewrite a scoped settings file for the
duration of a build. Plan review found the mechanism unverifiable by its
own tests (no way to introspect the CLI's effective `worktree.baseRef`
from a shell, nor to confirm a mid-session settings write actually
changes the next Agent-tool worktree spawn) and, worse, a crash before
restore would leak a silent, persistent override into unrelated
commands. The mechanism was dropped in favor of the detect-and-warn
design captured above. See
`plans/build-worktree-inherits-caller-head.md`'s "What changed from the
initial draft" section for the full rationale.

## Architecture Specification

### Components affected

- `plugins/dev-team/settings.json` — plugin-scoped settings that ship with the
  dev-team plugin. New top-level `worktree.baseRef: "head"` key.
- `plugins/dev-team/skills/build/SKILL.md` — orchestrator step that dispatches
  worktree subagents. Adds a pre-dispatch verification/fallback stage.
- `plugins/dev-team/scripts/build-wave-reconcile.sh` — merges wave slice
  branches back into the integration branch. Must be verified (and if
  necessary, adjusted) to carry the caller's WIP commits into the reconciled
  history alongside the slice diffs.
- `plugins/dev-team/agents/orchestrator.md` — text reference to the wave
  dispatch protocol; update to describe the base-ref contract.

### Interfaces

- **Setting**: `worktree.baseRef` (documented in Claude Code changelog entry
  around v2.1.140). Values: `fresh` (branch from `origin/<default>`) or `head`
  (branch from caller's local HEAD). Read by the Agent tool's worktree
  isolation and by `EnterWorktree`. Merges through the standard settings
  precedence: **project-local (`.claude/settings.local.json`) >
  project (`.claude/settings.json`) > user (`~/.claude/settings.json`) >
  plugin (`plugins/<name>/settings.json`)**. Higher precedence wins.
- **Environment**: `DEV_TEAM_WORKTREE_BASE_FRESH=1` silences `/build`'s
  detect-and-warn message when the user has deliberately chosen a
  non-`head` setting. The plugin default is the primary lever; the
  warning is a read-only guard, not a new knob for behavior.
- **Reconciler CLI**: `build-wave-reconcile.sh --into <integration> --base <ref>
  --test-cmd "<full suite>" <slice-branch>...` (unchanged surface; internal
  behavior may adjust to preserve WIP commits from `<integration>`).

### Dependencies

- Claude Code CLI version supporting `worktree.baseRef` (v2.1.140+ per
  changelog). No new external dependencies.
- Existing `hooks/pre-tool-guard.sh`, `hooks/context-ceiling-guard.sh`, and
  agent-model-resolve infrastructure are untouched.

### Constraints

- **No new tool surface.** The plugin uses only the existing `worktree.baseRef`
  setting; no changes to the Agent tool's interface are proposed here.
- **Backward compatible with user overrides.** A user who deliberately sets
  `worktree.baseRef: "fresh"` in their user- or project-scoped settings
  overrides the plugin default (standard precedence), but the `/build` runtime
  fallback still ensures worktrees spawned during a `/build` run branch from
  HEAD. If the user *wants* fresh-from-origin build worktrees, they can set
  the env var `DEV_TEAM_WORKTREE_BASE_FRESH=1` to disable the fallback (opt-out
  escape hatch).
- **Sequential fallback is unchanged.** Effective concurrency 1 already builds
  in a single worktree with no fan-out; the fix has no effect on that path.
- **No settings mutation at build time.** `/build`'s pre-dispatch check
  is read-only. It never writes a settings file. This constraint is what
  made the earlier force/restore design's crash-recovery risk moot: with
  no mutation, there is nothing to leak.
- **Portable shell.** Any script changes stay bash-3.2 safe and work on macOS,
  Linux, and Git Bash on Windows (per repo CLAUDE.md).

### Data flow

```
caller branch (issue-XXX)
├── docs/specs/<slug>.md   ← committed on issue-XXX
├── plans/<slug>.md        ← committed on issue-XXX
└── /build begins
    ├── detect worktree.baseRef; warn (do not mutate) if not head
    ├── dispatch wave 1 slices → each worktree branches from caller HEAD
    │   └── worktree sees the spec + plan naturally
    └── build-wave-reconcile.sh merges slice branches back
        └── caller's WIP commits (spec+plan) are already in the ancestry
```

## Acceptance Criteria

1. **Plugin default sets `worktree.baseRef` to `head`.** The shipped
   `plugins/dev-team/settings.json` contains `"worktree": {"baseRef": "head"}`
   at the top level. Verifiable by reading the file and by
   `jq '.worktree.baseRef' plugins/dev-team/settings.json` returning `"head"`.

2. **`/build` warns loudly on non-head base ref.** In a run where the
   effective `worktree.baseRef` resolves to `fresh` (or cannot be detected —
   the `unknown` sentinel), `/build` prints a warning naming the exact fix
   (edit user/project settings) and the opt-out env var, then continues. It
   does **not** mutate any settings file. Verifiable by a bats test that
   stubs the setting to `fresh` and asserts the warning tokens appear in
   the build output.

3. **Opt-out silences the warning.** With `DEV_TEAM_WORKTREE_BASE_FRESH=1`
   set, `/build` does not emit the warning — the user's setting is
   honored. Verifiable by a bats test that sets the env var and asserts
   no warning is emitted.

4. **Worktree subagents see the caller's WIP.** In a fixture repo where a
   commit on the current branch adds `docs/specs/<slug>.md` and
   `plans/<slug>.md`, a subagent dispatched with `isolation: "worktree"` under
   this plugin's settings sees both files at their expected paths without any
   `git checkout <sha> -- …` workaround. Verifiable by a bats test using the
   existing hermetic fixture infrastructure (`tests/lib/hermetic`) — spawn a
   worktree via the Agent tool's isolation contract and assert
   `test -f docs/specs/<slug>.md` in the child worktree.

5. **Reconciler preserves caller's WIP commits.** After
   `build-wave-reconcile.sh` merges all slice branches into the integration
   branch, the resulting history contains the caller's original WIP commits
   (the spec+plan commit) as ancestors of the reconciled tip. Verifiable by a
   bats test: seed a repo with a WIP commit, dispatch slice worktrees, run
   reconcile, and assert `git log --format=%H | grep <wip-sha>` succeeds on
   the integration branch.

6. **Documentation updated.** `plugins/dev-team/skills/build/SKILL.md`
   references the base-ref contract in Step 4 (concurrent dispatch), and
   `plugins/dev-team/agents/orchestrator.md`'s Wave-Aware Build Dispatch
   section names the contract. Verifiable by grep for the relevant phrase in
   both files.

7. **No regression in existing suites.** All existing bats tests still pass
   under `scripts/ci-local.sh` after the change.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Where the fix should live | `requires-stakeholder-input` | human | User chose "Both (recommend + fallback)": plugin default in settings.json plus a defensive `/build` verify-and-set. Belt-and-suspenders posture protects against user-level overrides silently reintroducing the bug. |
| Whether the reconciler needs its own change | `requires-stakeholder-input` | human | User chose "Yes — include in scope": verify `build-wave-reconcile.sh` carries the caller's WIP commits into the reconciled branch; if it does not, fix it. |
| Escape-hatch env var name | `inferable` | inference | Repo convention prefixes plugin env vars with `DEV_TEAM_` (see `DEV_TEAM_MAX_PARALLEL_BUILDS`, `DEV_TEAM_AUTO_APPROVE`, `DEV_TEAM_REVIEW_VALUE`). `DEV_TEAM_WORKTREE_BASE_FRESH=1` follows that pattern and reads naturally as "opt back into fresh". |
| Whether to touch the Agent tool's interface | `inferable` | inference | Explicit non-goal in the issue's "Not in scope" section (the async-agent output path issue is orthogonal). The `worktree.baseRef` setting already exists in Claude Code v2.1.140+; no new tool surface is required. |
| Behavior of the fallback: git config vs settings vs env | `inferable` | inference | `worktree.baseRef` is a Claude Code setting, not a git config. The fallback writes a scoped `.claude/settings.local.json` merge for the duration of the run and restores it at the end, or (simpler) sets `CLAUDE_CODE_WORKTREE_BASEREF=head` for the child process env if the CLI honors it. Concrete mechanism chosen during `/plan`; the acceptance criterion is behavioral (the audit line appears), not mechanistic. |
| Whether to fail loudly or silently when the fallback runs | `inferable` | inference | Repo convention is "loud halt, never silent" (see `/build` Step 4 sub-step 4). The fallback records an audit line but proceeds — matching the auto-approve pattern (`Auto-approved plan status …`). This is not an error; it is a corrected default. |
| Behavior when the caller has uncommitted (not-yet-committed) changes | `inferable` | inference | Out of scope. `head` refs a *commit*, not the index/worktree. Uncommitted changes never flow into a subagent worktree — the caller is expected to commit spec+plan before `/build` runs, which is already the `/ship` pipeline's convention (`/specs` and `/plan` both persist to disk and expect the caller to commit before `/build`). |
| Scope split: is this one feature or several | `inferable` | inference | Single feature: "worktree agents can see the caller's HEAD". The two layers (plugin default + `/build` fallback) and the reconciler check are three deliverables of the same behavior contract, exactly the vertical decomposition `/plan` will produce. Issue #553 explicitly deferred the two orthogonal observations (async output path, plan-waves parser) as separate issues if pursued. |
| `LOW_VALUE` items skipped | (none) | — | No low-value coverage gaps identified during critique. All acceptance criteria describe observable outcomes or file-level artifacts. |

## Consistency Gate

- [x] Intent is unambiguous — two developers would agree that "worktree
      subagents must inherit caller HEAD" is the goal.
- [x] Every behavior/goal maps to an acceptance criterion (defaults →
      criterion 1; fallback → 2, 3; visibility → 4; reconciler → 5;
      documentation → 6; no regression → 7).
- [x] Architecture constrains without over-engineering — reuses the existing
      `worktree.baseRef` setting; no new tool surface; portable shell.
- [x] Terminology consistent across artifacts (`worktree.baseRef`, `head`,
      `fresh`, `caller's HEAD`, `WIP commits`, `reconciler`).
- [x] No contradictions between artifacts.
- [x] Every gap/ambiguity finding is logged — the two `requires-stakeholder-input`
      items were resolved by the user before this file was written; every
      inference has a written rationale.
