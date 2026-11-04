---
name: lane
description: Work in an isolated lane (a linked worktree and branch), then land it on local trunk only when the reviewed tree, review gate, and trunk commit still match. Use for repositories without PRs, or when the user says "open a lane", "compose the lane", "integrate the lane", or "land this locally without a PR".
role: worker
user-invocable: true
allowed-tools: Read, Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane.py" *, git *)
---

# Lane

Role: worker. This command runs `lane.py` to open a lane, merge trunk into it, and fast-forward local trunk to it. It never pushes.

A lane is a linked worktree on its own branch. Trunk is `--trunk`, else the repository default (for example `origin/main`).

## Constraints

- Do not push. `integrate` changes local refs only; run `git push` yourself if you want it.
- Do not bypass git hooks, force anything, or edit the refusal text. Report each `refused:` block as printed.
- Do not retry a failed command in a loop. Read `why:` and `how:`, then fix the cause.
- Do not run `integrate` in a repository whose `origin` is on GitHub unless the human asks for `--local-trunk`. Use `/pr` instead.
- **Be concise.** Show the command output and the next step, no preamble.

## Arguments

Arguments: $ARGUMENTS

| Command | Arguments |
| --- | --- |
| `open` | `<name>`, optional `--path <dir>`, optional `--trunk <ref>` |
| `compose` | optional `--trunk <ref>` |
| `integrate` | `--expected-trunk <sha>`, `--expected-tree <sha>`, optional `--trunk <ref>`, optional `--local-trunk` |

Exit codes: 0 success, 1 refusal, 2 usage error.

## Steps

### 1. Open a lane

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane.py" open <name>
```

This creates a worktree beside the primary checkout (`<repo>-lane-<name>`) and a branch at the trunk tip. It prints `worktree:` and `branch:`. Work and commit inside the worktree.

### 2. Compose

Run `compose` inside the lane after you commit and fetch.

```bash
git fetch
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane.py" compose
```

`compose` merges trunk (and the local trunk branch, when it is ahead) into the lane. It prints the identities a reviewer holds: `expected-trunk:` and `expected-tree:` (both 40-hex), then a `next:` line. On a conflict or a rejected merge it restores the lane to the state it had before and prints no identities.

### 3. Review and integrate

The flow in a repository without PRs:

1. `open` the lane.
2. Work and commit in the lane.
3. `git fetch`.
4. `compose`.
5. Run `/code-review --since <trunk>` inside the lane. The review must see the composed tree.
6. `integrate`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane.py" integrate \
  --expected-trunk <expected-trunk> --expected-tree <expected-tree>
```

`integrate` runs every check, reports every failure in one pass, and changes nothing until all pass. It then:

1. Fast-forwards local trunk to the lane HEAD.
2. Removes the lane's review gate file.
3. Removes the lane worktree, including the ignored files inside it.
4. Deletes the lane branch.

On success it prints `trunk:`, `former-head:`, `now-at:`, `continue-in:`, `recover:`, and `pushed: nothing; run git push yourself if wanted`. The shell's current directory is gone, so run `cd` to the `continue-in:` path. To undo, run the `recover:` command (`git branch <lane> <former-head>`).

### 4. Pull request repositories

When `origin` is on GitHub, the flow is: `compose`, `/code-review`, then `/pr`. `compose` prints `next: open a PR with /pr` instead of an `integrate` line. `integrate` refuses with `PR repository`.

To land locally anyway, pass `--local-trunk` to `integrate`. `open` and `compose` ignore the origin.

### 5. Handle a partial failure

If a step fails after the checks pass, `integrate` stops and retries nothing. It prints an `integrate step failed` block, then:

- `done:` for each finished step (`nothing` when none finished).
- `remaining:` for each command to run by hand, in order.
- `recover:` for the command that restores the lane branch.

Re-running `integrate` is not the fix. Run the `remaining:` commands yourself.

## Refusals

Each refusal prints on stderr as `refused:`, `why:`, `how:`.

| Refusal | Cause | Fix |
| --- | --- | --- |
| `invalid lane name` | The name has characters or a form that git rejects. | Use letters, digits, `.`, `_`, `-`, and `/`, starting with a letter or digit. |
| `branch exists` | A branch with that name exists. | Choose another name, or run `git branch -d <name>` once it is merged. |
| `path exists` | The worktree path exists. | Pass `--path` with a new directory, or remove the old one. |
| `trunk ref cannot be resolved` | `--trunk` is not a commit, or no default trunk exists. | Pass `--trunk <ref>` or run `git remote set-head origin -a`. |
| `not a git repository` | The working directory is outside a git work tree. | Run `lane.py` from inside a git repository. |
| `not in a lane` | The directory is not a linked worktree on a non-trunk branch. | Create a lane with `open <name>`, then run the command inside it. |
| `lane has uncommitted changes` | The lane has staged, unstaged, or untracked paths, or a merge in progress. | Commit or stash the listed paths. For `.claude/` files, add `.claude/` to `.gitignore` (run `/setup`). |
| `compose conflict` | Merging trunk conflicts. The lane is restored. | Merge the named ref by hand in the lane, resolve, commit, and run `compose` again. |
| `compose merge failed` | Git rejected the merge (for example a hook). The lane is restored. | Resolve the cause in `why:`, then run `compose` again. |
| `compose restore unverified` | `compose` failed and could not confirm the lane is back at its starting commit. | Save your edits, then run the `git reset --hard <sha>` that `how:` names. |
| `tree mismatch` | The lane tree or HEAD differs from the reviewed identity. `expected:` and `live:` show both. | Run `compose` again, run `/code-review --since <trunk>` in the lane, and pass the new identities. |
| `review gate stale or missing` | No valid review gate covers the current diff. | Run `/code-review --since <trunk>` in the lane, then run `integrate` again. |
| `trunk moved` | The trunk commit differs from `expected-trunk`. | Run `compose` again, run `/code-review --since <trunk>` in the lane, and pass the new identities. |
| `trunk cannot fast-forward` | The local trunk branch is missing, not an ancestor of the lane, checked out nowhere, or dirty. `why:` names which. | Follow `how:`: pass `--trunk <branch>`, run `compose`, check out the branch, or clean its worktree. |
| `PR repository` | `origin` is on GitHub. | Open the PR with `/pr`, or pass `--local-trunk`. |
| `invalid identity argument` | An identity is not 40 lowercase hex characters. | Pass the unabbreviated values `compose` printed. |
| `integrate step failed` | An apply step failed after the checks passed. | Run the `remaining:` commands by hand. Do not re-run `integrate`. |
| `git command failed` | A git command failed, or the tool refused to build a forbidden one. | Fix the cause in `why:`, then run the named command again. |

## Output

Command output as printed. After `integrate` succeeds, report the new trunk commit, the `continue-in:` path, and that nothing was pushed.
