---
name: beads
description: Use Beads (bd) as the structured task tracker for all agent work. Replaces markdown TODO lists with a git-backed, dependency-aware issue graph that persists across sessions.
role: worker
user-invocable: true
---

# Beads Task Tracking Skill

Beads (`bd`) is a distributed, git-backed issue tracker designed for AI agents. It solves the "fresh context" problem: agents begin each session by querying `bd ready --json` to find their next unblocked task rather than relying on reconstructed context from prose summaries.

Use this skill whenever you need to track, discover, or coordinate work across sessions or agents.

## Constraints
- Run `bd init` once before first use in a project; commit `.beads/` to git
- Work one issue per session; start a fresh session for each `bd ready` item
- Always claim an issue (`--assignee`) before starting work in multi-agent scenarios
- Do not delete Beads issues; mark them `done` or `duplicate` instead

## Setup (one-time per project)

```bash
bd init
```

This creates a `.beads/` directory in the project root. Commit it alongside your code.

## Core Commands

| Command | Purpose |
|---------|---------|
| `bd ready` | List all unblocked tasks (no pending dependencies) |
| `bd ready --json` | Machine-readable list — use this in agent handoffs |
| `bd create "title" --body "details"` | Create a new issue |
| `bd update <id> --status done` | Mark an issue complete |
| `bd dep add <id> <depends-on-id>` | Add a dependency between issues |
| `bd show <id>` | View full issue detail |
| `bd list` | All open issues |
| `bd quickstart` | Print usage summary (useful at session start) |

IDs are short hashes (e.g. `bd-a1b2`) and are merge-conflict-safe.

## Workflow Integration

### Research Phase
As you explore the codebase, file issues for anything discovered that needs follow-up:

```bash
bd create "Fix broken test suite in auth module" \
  --body "Tests in src/auth/__tests__ are all failing. Root cause: missing mock for UserRepository."
bd create "Resolve N+1 query in OrderService.getAll" \
  --body "Found during research. Not in scope for current task but should be tracked."
```

Do not let discovered problems disappear when context is compacted. File them.

### Plan Phase
Decompose the implementation plan into discrete Beads issues. Link dependencies:

```bash
bd create "Implement UserRepository interface" --body "Port definition, no implementation yet"
bd create "Write SQL adapter for UserRepository" --body "Implements the port"
bd create "Write acceptance tests for user registration" --body "Gherkin scenarios from feature file"
bd dep add bd-c3d4 bd-a1b2  # SQL adapter depends on interface being defined first
bd dep add bd-e5f6 bd-a1b2  # tests depend on interface too
```

The plan progress file written to `memory/` should include the relevant Beads IDs so the next phase can query them directly.

### Implement Phase
At session start, find unblocked work:

```bash
bd ready --json
```

Work one issue at a time. When done:

```bash
bd update bd-a1b2 --status done
```

Re-query `bd ready --json` — newly unblocked tasks will now appear. Start a fresh session for each issue to keep context clean and decisions sharp.

## Session Discipline

Each Beads issue should map to roughly one focused agent session:
1. Start session → `bd ready --json` → pick first unblocked item
2. Do the work (read the issue, implement, test, review)
3. `bd update <id> --status done`
4. End session (let context window close)
5. Next session starts fresh with the next `bd ready` item

This is the primary value: short, high-quality sessions rather than one long degrading context.

## Multi-Agent Coordination

When multiple agents work in parallel, use assignee filtering to avoid collisions:

```bash
bd update bd-a1b2 --assignee software-engineer
bd ready --json --unassigned   # only show unclaimed tasks
```

Agents check `bd ready --json --unassigned` at session start and immediately claim their item before beginning work.

## Relationship Types

Use relationship metadata to capture intent:

```bash
bd dep add <id> <blocks-id>       # task A must complete before task B
bd relate <id> <related-id>       # informational link, no ordering
bd duplicate <id> <canonical-id>  # closes this as duplicate of canonical
```

## Integration with memory/ Progress Files

Beads and the `memory/` progress files serve complementary roles:
- **Beads**: structured, queryable task graph — the source of truth for *what work remains*
- **memory/ files**: prose context — the source of truth for *why decisions were made*

Phase transition progress files should include a section listing relevant Beads IDs:

```markdown
## Open Beads Issues
- bd-a1b2: Implement UserRepository interface (ready)
- bd-c3d4: Write SQL adapter (blocked by bd-a1b2)
- bd-e5f6: Write acceptance tests (blocked by bd-a1b2)
```

## Output
Updated Beads issue graph state: new issues created, dependencies linked, and status changes applied. Be concise — list issue IDs and their current status; omit command echoes.

## Installation

Beads is a system-wide CLI — install once, use across all projects:

```bash
npm install -g @beads/bd    # via npm
brew install beads           # via Homebrew
go install github.com/steveyegge/beads/cmd/bd@latest  # via Go
```

See the [Beads repository](https://github.com/steveyegge/beads) for full documentation.
