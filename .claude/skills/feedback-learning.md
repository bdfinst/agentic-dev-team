---
name: feedback-learning
description: Capture amend/learn/remember/forget keywords from the user and update agent or skill configurations. Invoke immediately when the user issues any of these trigger words — parse the change, preview a diff, apply it, and log it to the audit trail.
role: orchestrator
user-invocable: true
---

# Feedback & Learning

## Overview

Procedure for capturing user feedback, updating agent and skill configurations dynamically, and maintaining an audit trail of all changes. Enables continuous improvement without backend deployments.

## Trigger Keywords

Users trigger configuration changes using any of these keywords in natural language:

| Keyword | Intent | Example |
| --- | --- | --- |
| **amend** | Modify existing agent behavior or skill guidelines | `amend: the software engineer should prefer functional programming patterns` |
| **learn** | Teach the system something new for future use | `learn: our API conventions use kebab-case for URLs` |
| **remember** | Persist a preference or constraint across sessions | `remember: always run tests before completing implementation tasks` |
| **forget** | Remove a previously learned preference | `forget: the kebab-case URL convention` |

All four keywords follow the same processing flow. The distinction is semantic (helping the user express intent), not mechanical.

### Syntax

```
amend: [what to change]
learn: [what to teach]
remember: [what to persist]
forget: [what to remove]
```

### Examples

```
amend: increase the architect's autonomy for API design decisions
learn: our team uses PostgreSQL for all relational data
remember: always include accessibility checks in UI tasks
forget: the PostgreSQL preference, we're switching to MySQL
```

### Processing Flow

1. **Parse**: Orchestrator identifies the amend keyword and extracts the change request
2. **Classify**: Determine what type of change this is:

   | Change Type | Target File(s) | Approval Required |
   | --- | --- | --- |
   | Agent behavior tweak | `agents/{agent}.md` | No |
   | Skill guideline update | `skills/{skill}.md` | No |
   | New agent or skill | `agents/` or `skills/` + `CLAUDE.md` | Yes - confirm with user |
   | Team structure change | `CLAUDE.md` org chart + agent collaborators | Yes - confirm with user |
   | Orchestration rule change | `CLAUDE.md` processing flow | Yes - confirm with user |

3. **Preview**: Show the user the proposed change as a diff before applying
4. **Apply**: Make the edit to the target file(s)
5. **Log**: Record the change in the audit trail
6. **Verify**: Read back the modified section to confirm correctness

## Output
Preview diff of proposed change, confirmation of edit applied, and new changelog entry written. Be concise — show only the changed lines; omit file context outside the edit.

## Audit Trail

All configuration changes are logged in `metrics/config-changelog.jsonl` (one JSON object per line).

### Log Entry Format

```json
{
  "timestamp": "2026-02-20T14:30:00Z",
  "type": "amend",
  "trigger": "user",
  "description": "Updated software engineer to prefer functional programming patterns",
  "files_modified": ["agents/software-engineer.md"],
  "sections_modified": ["Psychological Profile"],
  "previous_value": "Work style: Detail-oriented, iterative, test-driven",
  "new_value": "Work style: Detail-oriented, iterative, test-driven, functional-first",
  "approved_by": "user"
}
```

### Log Entry Fields

| Field | Required | Description |
| --- | --- | --- |
| `timestamp` | Yes | ISO 8601 timestamp |
| `type` | Yes | `amend`, `learn`, `remember`, `forget`, `add`, `remove`, `restructure`, `rollback` |
| `trigger` | Yes | `user` (explicit amend) or `system` (learning loop) |
| `description` | Yes | Human-readable summary of the change |
| `files_modified` | Yes | List of file paths changed |
| `sections_modified` | Yes | Which sections within those files |
| `previous_value` | Yes | Content before the change |
| `new_value` | Yes | Content after the change |
| `approved_by` | Yes | `user` or `auto` (for low-risk changes) |

## Rollback

To undo a configuration change:

1. Read `metrics/config-changelog.jsonl` to find the change entry
2. Restore `previous_value` to the target file and section
3. Log the rollback as a new entry with `type: "rollback"`

### Rollback Syntax

```
amend: rollback the last change to software-engineer.md
amend: rollback all changes from today
```

## Learning Loop

After task completion, the Orchestrator evaluates whether configuration updates are warranted:

### Triggers for System-Initiated Changes

| Signal | Possible Action |
| --- | --- |
| Repeated user corrections on same topic | Update agent behavior or skill guidelines |
| Agent consistently defers to another agent | Adjust collaboration protocols |
| Skill applied but results rejected | Review skill guidelines for accuracy |
| Context summarization triggered frequently | Adjust loading profiles in context-loading-protocol |

### Process

1. Orchestrator identifies a recurring pattern (minimum 3 occurrences)
2. Proposes a config change to the user with rationale
3. User approves or rejects
4. If approved, apply and log with `trigger: "system"`

## Constraints

- Never modify files outside `.claude/` without explicit user instruction
- Never auto-apply changes without user preview for structural modifications
- Behavioral tweaks (tone, style) can be auto-applied; structural changes (new agents, removed skills, org chart) require approval
- The changelog is append-only; never delete entries
