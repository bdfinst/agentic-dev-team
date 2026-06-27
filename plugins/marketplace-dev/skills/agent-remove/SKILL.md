---
name: agent-remove
description: >-
  Remove an agent from the system — deletes the agent file, cleans up all
  registry entries, removes cross-references, and updates documentation.
  Use when the user says "remove the X agent", "delete X-review", "retire
  the X role", or "we no longer need X". Handles both team agents and review
  agents. Always confirms before deleting.
argument-hint: "<agent-name> [--plugin <dir>] [--dry]"
user-invocable: true
allowed-tools: Read, Edit, Bash(rm *), Bash(ls *), Bash(git rm *), Bash(grep -r *), Glob, Grep
---

# Agent Remove

Role: implementation. This skill removes an agent and all its references
from the system — it does not modify agent behavior or content.

You have been invoked with the `/agent-remove` skill. Fully remove a named
agent and update all required documentation.

## Implementation constraints

1. **Confirm before deleting.** Always show the user what will be removed
   and wait for confirmation before any destructive action.
2. **Detect agent type first.** Review agents (declare `Model tier:`) and
   team agents (declare persona sections) require different cleanup paths.
3. **Remove all references.** An agent that is deleted but still referenced
   in other files leaves the system in an inconsistent state.
4. **Always update documentation.** Documentation steps are mandatory.
   Review updated docs before reporting completion.
5. **Be concise.** Report only what changed. No narration of each step.

## Parse Arguments

Arguments: $ARGUMENTS

Required: agent name (`$0`) — the filename stem without `.md`
(e.g., `js-fp-review`, `security-engineer`)

Optional:

- `--plugin <dir>`: target plugin directory. Resolved as: this flag if given;
  else single `plugins/*/`; else cwd ancestor with `.claude-plugin/plugin.json`;
  else ask. Stored as `$PLUGIN`.
- `--dry`: Show what would be removed without making changes

## Steps

### 0. Resolve target plugin

Determine `$PLUGIN` using the convention above. Read
`$PLUGIN/.claude-plugin/plugin.json` and extract `name` as `$NAME`.

### 1. Locate agent file

Verify `$PLUGIN/agents/<name>.md` exists. If not, list all agent files
and report that the named agent was not found.

### 2. Detect agent type

Read `$PLUGIN/agents/<name>.md`:

- If it declares `Model tier:` → **review agent**
- Otherwise → **team agent**

### 3. Show removal plan

Display a confirmation prompt listing every action that will be taken:

```text
Remove agent: <name> (<type>) from $PLUGIN

Files to delete:
  - $PLUGIN/agents/<name>.md
  [review agents only — if eval fixtures exist at repo root]
  - evals/$NAME/fixtures/<name>-* (if any)
  - evals/$NAME/expected/<name>-* (if any)

Registry entries to remove:
  - $PLUGIN/knowledge/agent-registry.md: <table row> (if file exists)
  - $PLUGIN/CLAUDE.md: Quick Reference list entry (if section exists)
  [team agents only — if plugin maintains team-structure docs]
  - $PLUGIN/docs/team-structure.md: <diagram node and edges> (if file exists)

Documentation to update:
  - $PLUGIN/docs/agent_info.md: remove table row (if file exists)
  [team agents only]
  - $PLUGIN/agents/orchestrator.md: Tier guidance bullet (if listed)
  - Other agent files in $PLUGIN/agents/ referencing <name>

Proceed? (yes to continue)
```

If `--dry` was passed, display the plan and stop without waiting for
confirmation.

### 4. Remove agent file

```bash
git rm $PLUGIN/agents/<name>.md
```

If not in a git repository, use `rm`.

### 5. Clean up eval artifacts (review agents only)

Search for and remove matching eval fixtures and expected files at the repo
root under `evals/$NAME/`:

```bash
ls evals/$NAME/fixtures/ | grep <name>
ls evals/$NAME/expected/ | grep <name>
```

Remove each matching file with `git rm` (or `rm` if not in git). If the
`evals/$NAME/` directory does not exist, skip this step silently.

### 6. Update agent registry

If `$PLUGIN/knowledge/agent-registry.md` exists, remove the agent's row
from the appropriate table (Team Agents or Review Agents). If the file
does not exist, skip this step.

### 7. Update plugin CLAUDE.md

If `$PLUGIN/CLAUDE.md` exists:

- Remove the agent from the Quick Reference list (decrement the count and
  remove the name from the comma-separated list)
- Remove from the Skills Registry table if listed

If the file does not exist, skip this step.

### 8. Update orchestrator agent (team agents only)

If `$PLUGIN/agents/orchestrator.md` exists:

- Remove the agent name from any "Tier guidance (informational)" bullet list
- Remove from any Inline Review Checkpoint table if listed

If the file does not exist, skip this step.

### 9. Update cross-references in other agent files

Search for references to the removed agent:

```bash
grep -r "<name>" $PLUGIN/agents/ --include="*.md" -l
```

For each file found, remove or update:

- Collaboration protocol entries that name the removed agent
- Skills section references (if a team agent was referenced as a skill)

### 10. Update docs/agent_info.md (if it exists)

If `$PLUGIN/docs/agent_info.md` exists:

- Remove the agent's row from the Team Agents or Review Agents table
- If removing a team agent, remove any "Primary Collaborators" references
  in prose sections

If the file does not exist, skip this step.

### 11. Update team-structure docs (team agents only, if they exist)

If `$PLUGIN/docs/team-structure.md` exists, remove the agent node and all
its edges from any Mermaid diagrams in that file. If the file does not
exist, skip this step.

### 12. Review documentation

Review all modified documentation files for accuracy and consistency before
reporting completion. Specifically check:

- No dangling references to the removed agent remain in any doc
- Tables are consistent across CLAUDE.md and docs/
- Any Mermaid diagrams render correctly (no orphaned edges)

### 13. Report

```text
Agent removed: <name> (<type>) from $PLUGIN

Deleted:
  - $PLUGIN/agents/<name>.md
  [+ eval files if any]

Updated:
  - $PLUGIN/knowledge/agent-registry.md [or: skipped — file not found]
  - $PLUGIN/CLAUDE.md [or: skipped — file not found]
  [+ orchestrator.md, team-structure.md, cross-references as applicable]

Documentation is consistent.
```
