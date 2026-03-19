---
name: upgrade
description: >-
  Check for and apply plugin updates. Pulls the latest version, shows what
  changed, and applies the update from within a Claude Code session.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(git *), Bash(gh *)
---

# Upgrade

Role: worker. This command updates the agentic-dev-team plugin to the latest version.

You have been invoked with the `/upgrade` command.

## Steps

### 1. Detect plugin location

Determine where the plugin is installed by checking the current working directory and common install paths:

```bash
# Check if we're in the plugin repo itself (development mode)
git -C . rev-parse --is-inside-work-tree 2>/dev/null && git -C . remote get-url origin 2>/dev/null
```

Look for `agentic-dev-team` in the remote URL. If not found, check:
- `~/.claude/plugins/agentic-dev-team/`
- `.claude/plugins/agentic-dev-team/`

If no git repo is found at any of these locations:
> This plugin appears to be a vendored copy (not a git clone). To upgrade:
> 1. Remove the current copy
> 2. Re-clone from the repository
>
> Or run: `claude plugin install agentic-dev-team`

Exit without making changes.

### 2. Check for local modifications

```bash
git status --porcelain
```

If there are local modifications:
> **Warning**: You have local modifications in the plugin directory:
> ```
> <git status output>
> ```
> These changes will need to be stashed or committed before upgrading.
> Proceed with stash? (Stashed changes can be restored with `git stash pop`)

Wait for user confirmation before proceeding. If confirmed, run `git stash`.

### 3. Fetch and check for updates

```bash
git fetch origin
git log HEAD..origin/main --oneline
```

If no commits are ahead:
> Already up to date. You're running the latest version.

Exit without making changes.

### 4. Show what changed

```bash
git diff HEAD..origin/main --stat
```

Categorize the changes:
- **Agents**: Files in `agents/` (new, modified, removed)
- **Skills**: Files in `skills/` (new, modified, removed)
- **Commands**: Files in `commands/` (new, modified, removed)
- **Hooks**: Files in `hooks/` (new, modified, removed)
- **Knowledge**: Files in `knowledge/` (new, modified, removed)
- **Other**: Everything else

Display a summary:
```
## Available Update

**Commits**: <N> new commits
**Files changed**: <N>

### Changes by category
- Agents: <N> modified, <N> new
- Skills: <N> modified, <N> new
- Commands: <N> modified, <N> new
- Hooks: <N> modified
- Other: <N> files

### New features
<List any new commands or agents added>

### Breaking changes
<List any removed files or renamed commands, or "None detected">
```

### 5. Confirm with user

> Apply this update? This will pull <N> commits from origin/main.

Wait for user confirmation.

### 6. Apply update

```bash
git pull origin main
```

### 7. Post-upgrade summary

Display:
```
## Upgrade Complete

Updated to: <new commit hash> (<commit message>)
Previous:   <old commit hash>

<If stash was used>: Run `git stash pop` to restore your local modifications.
```

If new commands were added, list them so the user knows they're available.

## Edge Cases

- **Detached HEAD**: Warn the user and suggest checking out a branch first
- **Merge conflicts**: Report the conflict and suggest manual resolution
- **Network errors**: Report the fetch failure and suggest checking connectivity
- **Non-main branch**: If on a feature branch, offer to merge main or rebase
