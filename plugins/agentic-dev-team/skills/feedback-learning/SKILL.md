---
name: feedback-learning
description: Capture amend/learn/remember/forget keywords from the user and update agent or skill configurations. Invoke immediately when the user issues any of these trigger words — parse the change, preview a diff, apply it, and log it to the audit trail.
role: orchestrator
user-invocable: true
---

# Feedback & Learning

Procedure for capturing user feedback, updating configurations dynamically, and maintaining an audit trail of all changes.

## Trigger Keywords

| Keyword | Intent | Example |
| --- | --- | --- |
| **amend** | Modify existing behavior | `amend: the software engineer should prefer functional patterns` |
| **learn** | Teach something new | `learn: our API uses kebab-case URLs` |
| **remember** | Persist a preference across sessions | `remember: always run tests before completing tasks` |
| **forget** | Remove a previous preference | `forget: the kebab-case URL convention` |

All four follow the same processing flow. The distinction is semantic (helping the user express intent), not mechanical.

## Where Changes Are Written

The plugin ships as a read-only cache — agent and skill files inside the plugin cannot be edited. Instead, feedback is persisted to **project-local files** that the user controls and that Claude Code loads automatically.

### Resolution order

When processing a feedback keyword, determine the right destination:

| Change type | Write to | Why |
| --- | --- | --- |
| Project convention or preference | **Project `CLAUDE.md`** (`.claude/CLAUDE.md` or repo-root `CLAUDE.md`) | Loaded every session, applies to all agents |
| Review context (domain knowledge, known issues, team norms) | **`REVIEW-CONTEXT.md`** in project root | Read by `/code-review` and passed to every review agent |
| Agent behavior override for this project | **Project `CLAUDE.md`** under a `## Agent Overrides` section | Overrides plugin defaults without editing plugin files |
| Cross-session memory (decisions, project state) | **`memory/`** files | Persists across context resets |
| Rollback a previous change | Reverse the edit in whichever file it was written to | Logged as `type: "rollback"` |

### What NOT to do

- Do not edit files inside the plugin cache (`~/.claude/plugins/cache/...`). Changes there are overwritten on plugin updates.
- Do not create new agent or skill files in the project. Instead, add override instructions to project `CLAUDE.md`.

### Project CLAUDE.md structure for overrides

When writing agent behavior overrides, add them under a dedicated section so they're easy to find and manage:

```markdown
## Agent Overrides

### Software Engineer
- Prefer functional programming patterns over OOP
- Always use `const` over `let` in JavaScript

### Architect
- Default to event-driven architecture for new services
```

These instructions are loaded into every session and take precedence over the plugin's built-in agent definitions because project `CLAUDE.md` is processed after plugin files.

## Processing Flow

1. **Parse**: Identify the trigger keyword and extract the change request
2. **Classify**: Determine change type using the resolution table above
3. **Preview**: Show the user the proposed edit as a diff before applying
4. **Apply**: Write the change to the target file
5. **Log**: Record the change in the audit trail
6. **Verify**: Read back the modified section to confirm correctness

### Approval rules

- Preference and convention changes: apply after diff preview
- New sections or structural edits to CLAUDE.md: require explicit approval
- Rollbacks: apply after confirming which change to reverse

## Audit Trail

All changes are logged in `metrics/config-changelog.jsonl` (one JSON object per line, append-only).

```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "type": "amend",
  "trigger": "user",
  "description": "Updated software engineer to prefer functional patterns",
  "file_modified": "CLAUDE.md",
  "section_modified": "Agent Overrides > Software Engineer",
  "previous_value": "",
  "new_value": "- Prefer functional programming patterns over OOP",
  "approved_by": "user"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `timestamp` | Yes | ISO 8601 |
| `type` | Yes | `amend`, `learn`, `remember`, `forget`, `rollback` |
| `trigger` | Yes | `user` or `system` (learning loop) |
| `description` | Yes | Human-readable summary |
| `file_modified` | Yes | Path of the file changed |
| `section_modified` | Yes | Which section within the file |
| `previous_value` | Yes | Content before (empty string if new) |
| `new_value` | Yes | Content after (empty string if removed) |
| `approved_by` | Yes | `user` or `auto` |

## Rollback

```
amend: rollback the last change to CLAUDE.md
amend: rollback all changes from today
```

1. Read `metrics/config-changelog.jsonl` to find the entry
2. Restore `previous_value` to the target file and section
3. Log the rollback as a new entry with `type: "rollback"`

## Learning Loop

After task completion, the orchestrator captures learnings in two ways:

### Post-task reflection

After completing a feature or fixing a complex bug, review the git diff and any review feedback and ask: "What do I wish I'd known at the start?" Classify each insight:

| Category | Example |
| --- | --- |
| **Gotcha** | "The API returns 200 with an error body" |
| **Pattern** | "Use factory functions for test fixtures" |
| **Anti-pattern** | "Don't mock the database for integration tests" |
| **Decision** | "Chose event sourcing over CRUD for audit trail" |
| **Edge case** | "Empty arrays and null are treated differently by the serializer" |

Only capture non-obvious insights — if it's clear from reading the code, skip it. Present proposals to the user; persist approved ones using the resolution table above. Log with `trigger: "system"`.

### Recurring correction detection

The orchestrator also watches for patterns across tasks:

| Signal | Possible action |
| --- | --- |
| 3+ user corrections on same topic | Propose a project CLAUDE.md update |
| Agent consistently defers to another | Propose collaboration protocol tweak |
| Skill results repeatedly rejected | Propose skill guideline override |
| Context summarization triggered frequently | Propose loading profile adjustment |

When a pattern is detected (minimum 3 occurrences), propose the change with rationale. User approves or rejects. If approved, apply and log with `trigger: "system"`.

## Constraints

- Never edit plugin cache files — all changes go to project-local files
- Never auto-apply without user preview for structural modifications
- Behavioral tweaks (tone, preferences) can be auto-applied; structural changes (new sections, removed overrides) require approval
- The changelog is append-only — never delete entries
