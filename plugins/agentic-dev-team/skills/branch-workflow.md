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

## Workflow

### 1. Pre-PR Checklist
Before creating the PR, verify:
- [ ] All tests pass (fresh run, not cached)
- [ ] `/code-review --changed` passed or warnings are documented
- [ ] Documentation is current (tech-writer verified in Phase 3)
- [ ] Branch is rebased on latest main (resolve conflicts if needed)

### 2. Create the PR
- Title: concise, under 70 characters, describes the change
- Body: Summary (what and why), test plan, link to design doc if one exists
- Labels: add relevant labels (bug, feature, refactor, docs)
- Reviewers: assign based on who should review (human decides)

### 3. Present Options

After confirming the base branch, present exactly four choices:

1. **Merge locally** — Integrate feature branch into base, run tests on merged result, delete feature branch and worktree
2. **Push and create PR** — Push branch and create pull request via `gh pr create`. Keep worktree (PR still in progress)
3. **Keep as-is** — Preserve branch and worktree for later handling
4. **Discard** — Permanently delete branch and all commits. **Requires the human to type "discard" to confirm.** Never discard without typed confirmation.

### 4. Merge Strategy (for options 1 and 2)

| Situation | Strategy | Why |
|-----------|----------|-----|
| Single logical change, clean history | Squash merge | One commit tells the story |
| Multiple logical changes that should stay separate | Merge commit | Preserves the history of each change |
| Long-lived branch with many commits | Squash merge | Reduces noise in main history |
| Experimental/spike work | Squash merge | The journey doesn't matter, only the result |

Default: **squash merge** unless the human specifies otherwise.

### 5. Post-Merge Verification & Cleanup
- Run tests on the merged result — **do not skip this**. Broken code must never reach base branches.
- Delete the feature branch (remote and local) — only for options 1 and 4
- Remove worktree if applicable (options 1 and 4 only; keep for option 2)

## Integration
- Triggered after Phase 3 human gate approval
- PR creation follows the git commit conventions in the project

## Output
A merged PR with clean branch history, closed issues, and deleted feature branch.
