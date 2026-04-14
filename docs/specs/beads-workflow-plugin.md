# Specification: Beads Workflow Plugin

**Created**: 2026-04-14
**Status**: draft

## Intent Description

**What**: Create a companion plugin (`beads-workflow`) that replaces the agentic-dev-team plugin's file-based task/plan state management with [Beads](https://github.com/gastownhall/beads), a distributed, version-controlled task tracking system built on Dolt.

**Why**: The agentic-dev-team plugin currently uses markdown files as a pseudo-database for plan execution state. Plan steps are checkboxes in `.md` files, progress is tracked by reading/writing text, cross-session continuity relies on reconstructing state from `memory/` files, and there is no dependency tracking between steps. Beads provides atomic task state, dependency graphs, audit trails, and queryable history — solving these limitations without modifying the base plugin.

**Scope**: A separate plugin (`beads-workflow`) that users install alongside `agentic-dev-team`. It provides alternative `/plan`, `/build`, and `/continue` commands backed by Beads. The base plugin is unchanged. Beads/Dolt are required dependencies of the new plugin only.

## User-Facing Behavior

```gherkin
Feature: Beads-backed plan creation

  Scenario: Plan steps are created as beads
    Given the beads-workflow plugin is installed
    And the agentic-dev-team plugin is installed
    And dolt and bd CLI tools are available on PATH
    When the user runs /beads-workflow:plan with a task description
    Then a bead graph is created with one bead per plan step
    And dependencies between steps are recorded via bd dep add
    And a human-readable markdown plan is also written to plans/{slug}.md
    And the plan markdown includes bead IDs next to each step

  Scenario: Plan with parallel steps records no dependency between them
    Given a plan has steps A, B, and C
    And steps A and B are independent
    And step C depends on both A and B
    When the plan is created as beads
    Then step A has no dependency on step B
    And step C has dependencies on both step A and step B

Feature: Beads-backed plan execution

  Scenario: Build queries beads for next step
    Given an approved plan exists as a bead graph
    When the user runs /beads-workflow:build
    Then the skill runs bd ready to find unblocked steps
    And begins implementing the first unblocked step
    And runs bd update <id> --done when the step passes

  Scenario: Parallel steps are dispatched to worktrees
    Given bd ready returns multiple unblocked steps
    When the build skill processes the next batch
    Then independent steps are dispatched as parallel worktree sub-agents
    And each sub-agent runs bd update <id> --claim before starting
    And each sub-agent runs bd update <id> --done on completion

  Scenario: Failed step blocks dependents
    Given step A is in progress and step B depends on step A
    When step A fails its tests
    Then step A remains in an open state
    And bd ready does not return step B

Feature: Beads-backed session continuity

  Scenario: Continue from a prior session
    Given a bead graph exists with some steps completed and some open
    When the user runs /beads-workflow:continue
    Then the skill runs bd ready to find unblocked work
    And presents the user with a summary of completed vs remaining steps
    And resumes execution from the first unblocked step

  Scenario: Continue with no prior beads state
    Given no .beads/ directory exists in the project
    When the user runs /beads-workflow:continue
    Then the skill falls back to the base plugin behavior
    And reads memory/ files for session state

Feature: Prerequisite validation

  Scenario: Missing dolt CLI
    Given dolt is not installed
    When the user attempts to install the beads-workflow plugin
    Then install.sh exits with an error message explaining dolt is required
    And provides the installation URL for dolt

  Scenario: Missing bd CLI
    Given bd is not installed
    When the user attempts to install the beads-workflow plugin
    Then install.sh exits with an error message explaining beads is required
    And provides the installation URL for beads

  Scenario: Missing base plugin
    Given the agentic-dev-team plugin is not installed
    When the user runs any /beads-workflow command
    Then the skill outputs an error explaining the base plugin is required
```

## Architecture Specification

### Plugin Structure

```
plugins/beads-workflow/
├── .claude-plugin/plugin.json       # Plugin manifest
├── CLAUDE.md                        # Plugin instructions
├── install.sh                       # Prerequisite checker (dolt, bd)
├── skills/
│   ├── beads-plan.md                # Extends agentic-dev-team:plan with bd state
│   ├── beads-build.md               # Uses bd ready/claim/done for execution
│   ├── beads-continue.md            # Uses bd ready for session resume
│   └── beads-primitives.md          # Reusable bd CLI wrappers
└── commands/
    ├── plan.md                      # Routes to beads-plan skill
    ├── build.md                     # Routes to beads-build skill
    └── continue.md                  # Routes to beads-continue skill
```

### Relationship to Base Plugin

The beads-workflow plugin is **additive, not replacing**. Both plugins are installed. Users choose which command namespace to invoke:

| Workflow | File-based (base) | Beads-backed (this plugin) |
|----------|-------------------|---------------------------|
| Plan | `/agentic-dev-team:plan` | `/beads-workflow:plan` |
| Build | `/agentic-dev-team:build` | `/beads-workflow:build` |
| Continue | `/agentic-dev-team:continue` | `/beads-workflow:continue` |
| Code review | `/agentic-dev-team:code-review` | (unchanged, uses base) |
| All other commands | `/agentic-dev-team:*` | (unchanged, uses base) |

The beads plugin **does not duplicate** review agents, team agents, hooks, or knowledge files. It only replaces the state-tracking layer for plan/build/continue.

### State Mapping

| Concept | Base plugin (markdown) | Beads plugin |
|---------|----------------------|--------------|
| Plan step | Checkbox in `plans/{slug}.md` | Bead with status (open/in-progress/done) |
| Step dependency | Implicit (sequential order) | Explicit (`bd dep add`) |
| Step assignment | N/A (single agent) | `bd update <id> --claim` (multi-agent safe) |
| Step completion | Edit checkbox to `[x]` | `bd update <id> --done` |
| Next work query | Read markdown, find first unchecked | `bd ready` |
| Plan status | `status: draft\|approved\|implemented` field | Parent bead status + child rollup |
| Cross-session state | `memory/` progress files | `.beads/` Dolt database |
| Audit trail | Git history of plan file | Dolt commit log per bead |

### Beads Initialization

When `/beads-workflow:plan` runs and no `.beads/` directory exists, it initializes:

```bash
bd init              # Creates .beads/ with embedded Dolt database
```

The `.beads/` directory should be added to `.gitignore` by default (task state is local), with an opt-in `bd push` workflow for shared state documented in the plugin's CLAUDE.md.

### Skill Design: Extending Base Skills

Each beads skill prompt follows this pattern:

1. Read the corresponding base skill (e.g., `agentic-dev-team:plan`) for the full workflow
2. Follow all base skill instructions (TDD steps, plan review personas, human gates)
3. **Replace** file-based state operations with Beads equivalents
4. **Additionally** write a human-readable markdown plan (dual-write for reviewability)

This means the beads plugin inherits improvements to the base skills automatically — the agent reads the current base skill at runtime, not a frozen copy.

### Multi-Agent Coordination

Beads enables safe parallel execution that the base plugin cannot provide:

1. `bd ready` returns all unblocked steps (not just the next one)
2. Each worktree sub-agent runs `bd update <id> --claim` atomically before starting
3. If two agents race for the same step, one wins and the other skips it
4. Dolt's embedded mode supports single-writer; **server mode is required for true parallel writes**

For v1, parallel execution uses embedded mode with serialized `bd` calls from the parent orchestrator. Server mode is a future enhancement.

## Acceptance Criteria

1. A user with both plugins installed can run `/beads-workflow:plan` and get a bead graph plus markdown plan
2. `/beads-workflow:build` uses `bd ready` to determine next steps and `bd update --done` on completion
3. `/beads-workflow:continue` resumes from bead state without reading `memory/` files
4. All base plugin behaviors (TDD, plan review personas, human gates, inline reviews) are preserved
5. The base `agentic-dev-team` plugin is completely unmodified
6. `install.sh` validates `dolt` and `bd` are on PATH before allowing installation
7. `.beads/` is initialized on first plan creation if not present
8. Plan markdown is always written alongside bead state (dual-write)

## Open Questions

1. **`.beads/` in git?** Default to `.gitignore` (local state), but teams may want shared state via `dolt push`. Should the plugin support both modes from v1?
2. **Server mode for parallel writes?** Embedded Dolt is single-writer. True worktree parallelism needs server mode. Is this a v1 requirement or deferred?
3. **Migration path?** Should `/beads-workflow:continue` detect existing markdown-only plans and offer to import them as beads?
4. **Bead compaction?** Beads supports memory decay for closed tasks. Should completed plan steps be compacted after the plan is fully implemented?
5. **Base plugin awareness?** Should the base plugin's `/plan` eventually detect beads and suggest using `/beads-workflow:plan` instead? This would be a small change to the base plugin.
