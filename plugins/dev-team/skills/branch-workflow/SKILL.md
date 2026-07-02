---
name: branch-workflow
description: Clean branch completion workflow — PR creation, merge strategy, and cleanup. Use this skill when implementation is complete and it's time to ship — after Phase 3 human gate passes. Also use when the user says "create a PR", "merge this", "ship it", "finish this branch", or asks about merge strategy.
role: worker
user-invocable: true
---

# Branch Workflow

## Overview

The three-phase workflow ends at the Phase 3 human gate. This skill formalizes what happens after approval: PR creation, merge decision, and branch cleanup. Without this, branches linger and merge conflicts accumulate.

## Constraints

- Do not push to main/master directly — always use a PR
- Do not force-push unless the human explicitly requests it
- Do not delete branches that have unmerged work
- Do not merge without a passing CI check (if CI is configured)
- Do not switch branches (checkout, worktree enter) without first checking working-tree state and confirming with the human if dirty

## Workflow

### 1. Pre-PR Checklist

Before creating the PR, verify:

- [ ] All tests pass (fresh run, not cached)
- [ ] `/code-review` passed or warnings are documented
- [ ] Documentation is current (tech-writer verified in Phase 3)
- [ ] Branch is rebased on latest main (resolve conflicts if needed)

### 2. Create the PR

- Title: concise, under 70 characters, describes the change
- Body: Summary (what and why), test plan, link to design doc if one exists
- Labels: add relevant labels (bug, feature, refactor, docs)
- Reviewers: assign based on who should review (human decides)

### 3. Present Options

After confirming the base branch, present exactly four choices. If this session entered a worktree via `EnterWorktree` for this branch, each option's cleanup step is performed with the paired `ExitWorktree` call below — never raw `git worktree remove`. If no worktree was entered via `EnterWorktree` (branch-workflow can also run directly in the primary checkout), the `ExitWorktree` steps are a no-op — skip them.

1. **Merge locally** — Integrate feature branch into base, run tests on merged result, delete feature branch, then call `ExitWorktree(action="remove")`
2. **Push and create PR** — Push branch and create pull request via `gh pr create`. Once the PR is opened, call `ExitWorktree(action="keep")` so the worktree persists on disk while the session's CWD bookkeeping is closed
3. **Keep as-is** — Preserve branch and worktree for later handling; call `ExitWorktree(action="keep")` immediately after the option is confirmed — do not leave the worktree silently "entered" for the rest of the session
4. **Discard** — Permanently delete branch and all commits. **Requires the human to type "discard" to confirm.** Never discard without typed confirmation. After confirmation, call `ExitWorktree(action="remove", discard_changes=true)`

### 3a. Pre-Switch Verification (Option 1 only)

Before performing the checkout/merge that Option 1 ("Merge locally") requires, verify the working tree is safe to switch:

1. Run a working-tree status check (`git status --short`, or the worktree-tool equivalent) covering the feature branch's tree. This surfaces both tracked changes (modified/staged) and untracked files — not just tracked ones.
2. Show the result to the human.
3. If the tree is clean, proceed with the switch.
4. If the tree is **not** clean (any modified, staged, or untracked files), stop. Do not switch branches silently. Require the human to explicitly say how to proceed — commit, stash, or abort — before running the checkout. This follows the same explicit-confirmation pattern as Option 4's typed "discard," not a bare warning that can be clicked through.
5. Re-check that the target/base branch still matches what was confirmed in step 3's "After confirming the base branch..." — this does not re-ask for that confirmation, only verifies it hasn't drifted since.

This step applies only to the branch/worktree switch Option 1 performs. It does not replace or duplicate the Pre-PR Checklist's "Branch is rebased on latest main" item (§1) — that is a rebase-currency check performed earlier, not a dirty-tree check performed at the moment of switching. It also does not modify Post-Merge Verification & Cleanup (§5), which handles branch/worktree deletion after the merge, not the switch before it.

### 4. Merge Strategy (for options 1 and 2)

| Situation | Strategy | Why |
| ----------- | ---------- | ----- |
| Single logical change, clean history | Squash merge | One commit tells the story |
| Multiple logical changes that should stay separate | Merge commit | Preserves the history of each change |
| Long-lived branch with many commits | Squash merge | Reduces noise in main history |
| Experimental/spike work | Squash merge | The journey doesn't matter, only the result |

Default: **squash merge** unless the human specifies otherwise.

### 5. Post-Merge Verification & Cleanup

- Run tests on the merged result — **do not skip this**. Broken code must never reach base branches.
- Delete the feature branch (remote and local) — only for options 1 and 4
- If a worktree was entered via `EnterWorktree` for this branch, call `ExitWorktree(action="remove")` for options 1 and 4 (never raw `git worktree remove`); options 2 and 3 use `ExitWorktree(action="keep")` as described in Section 3. If no worktree was entered via `EnterWorktree`, this step is a no-op.
- After removal, verify no orphaned worktree or branch remains — e.g. `git worktree list` and `git branch` should show nothing for the deleted branch

## Integration

- Triggered after Phase 3 human gate approval
- PR creation follows the git commit conventions in the project

## Output

A merged PR with clean branch history, closed issues, and deleted feature branch.
