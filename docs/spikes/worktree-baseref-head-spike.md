# Spike: verify `worktree.baseRef=head` changes Agent-tool worktree base ref

**Date**: 2026-07-01T21:36:51Z
**Claude Code CLI**: 2.1.198
**Caller branch**: `fixes` at `ce335f0` (WIP commit `chore(build): spec+plan for issue #553 worktree.baseRef fix`)
**`origin/main` HEAD**: `b65e90e`
**Purpose**: gate Slices 1–4 of `plans/build-worktree-inherits-caller-head.md`. The plan proposed shipping `worktree.baseRef: "head"` in `plugins/dev-team/settings.json`. Slice 0 verifies that this setting, at that scope, actually changes what an `isolation: "worktree"` subagent sees.

## Method

For each candidate settings scope, drop the key
`{"worktree": {"baseRef": "head"}}`, dispatch an `Agent` tool call with
`isolation: "worktree"` and `subagent_type: "claude"`, ask it to report
`pwd`, `git rev-parse HEAD`, and whether the caller's WIP files exist in
its worktree, then restore the scope's original file byte-for-byte before
testing the next scope.

## Results

| Scope | Settings file | Child worktree HEAD | `docs/specs/…` visible? | `plans/…` visible? | Verdict |
|---|---|---:|:-:|:-:|---|
| (control — no `worktree.baseRef` anywhere) | — | `b65e90e` (origin/main) | ❌ | ❌ | reproduces #553 |
| project-local | `.claude/settings.local.json` | `b65e90e` | ❌ | ❌ | **not honored** |
| user | `~/.claude/settings.json` | `ce335f0` (caller HEAD) | ✅ | ✅ | honored |
| project | `.claude/settings.json` | `ce335f0` (caller HEAD) | ✅ | ✅ | honored |
| plugin | `plugins/dev-team/settings.json` | `b65e90e` | ❌ | ❌ | **not honored** |

## Findings

1. **The `worktree.baseRef: "head"` setting exists and works** — at
   user (`~/.claude/settings.json`) and project (`.claude/settings.json`)
   scopes. When present, a subagent worktree branches from the caller's
   local HEAD instead of `origin/<default>`, and the caller's
   uncommitted-to-remote files are visible without any `git checkout
   <sha> --` workaround.
2. **Plugin-scope settings are NOT honored** for this key. Setting
   `worktree.baseRef: "head"` in `plugins/dev-team/settings.json` had no
   observable effect. **This invalidates the plan's original Slice 1
   design.** Two hypotheses (not verified here — out of spike scope):
   (a) plugin `settings.json` only merges `permissions` and `hooks`, not
   arbitrary top-level keys like `worktree`; (b) the setting is read at
   session boot and plugin files are picked up on a different code path.
3. **Project-local (`.claude/settings.local.json`) is also NOT honored**
   for this key — surprising because `.local.json` is typically the
   highest-precedence settings file. This may be a bug in Claude Code
   2.1.198's settings merger, or `.local.json` may deliberately exclude
   `worktree.baseRef`. Not gated further here.

## Impact on the plan

Slice 1 as written (put the key in `plugins/dev-team/settings.json`)
would ship a no-op — every user of the plugin would still get
`fresh`-based worktrees and #553 would still reproduce. The plan needs
one of:

- **Option A**: change Slice 1 to write to `.claude/settings.json`
  instead. This is a project-scope setting the plugin cannot own on
  behalf of every project using it. Effectively "document that users
  should set this themselves in their project" — Slice 2's warning
  becomes the primary lever.
- **Option B**: change Slice 1 to write to `~/.claude/settings.json` via
  a first-run hook or `install.sh`. Cross-cutting side effect on the
  user's global settings — needs its own review.
- **Option C**: file an upstream Claude Code issue asking that
  `worktree.baseRef` be honored from plugin settings, and in the
  meantime **drop Slice 1 entirely** — rely on Slice 2's warning to tell
  the user how to set it themselves in their project or user settings.
  This is the simplest correct answer if the CLI's plugin-settings merge
  scope is a deliberate design constraint rather than a bug.

## Halt condition

**Halted.** Escalating to the human per the plan's Slice 0 halt clause.
Do not proceed to Slices 1–4 until the plan is updated to reflect the
observed settings-scope constraint.

## Verbatim subagent outputs

Preserved in the `/build` session transcript that produced this file.
Every worktree was created by the Agent tool with
`isolation: "worktree"` and disposed of on subagent exit — no manual
`git worktree add` was used.
