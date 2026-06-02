# Spec: /triage — File-Based Triage Records

## Intent Description

The `/triage` command currently concludes by creating a GitHub issue via `gh issue create`. This
couples bug tracking to GitHub, preventing the command from working in projects that use Jira,
Linear, GitLab, or no issue tracker at all.

This change replaces the GitHub issue creation step with writing a structured markdown file to
`.triage/<slug>.md` in the project root. The file preserves all content currently in the GitHub
issue body (problem statement, root cause analysis, TDD fix plan, acceptance criteria) and adds
YAML frontmatter for machine-readability (id, created timestamp, status). The `.triage/` directory
becomes a lightweight, portable issue store that lives in the repository alongside the code it
describes.

The command's investigation workflow (reproduce → investigate → root cause → design fix plan) is
unchanged. Only the output step changes. GitHub integration, if desired, becomes an explicit
downstream step — a hook, a sync command, or a manual `gh issue create` from the file — rather
than a hard dependency baked into triage itself.

---

## User-Facing Behavior

```gherkin
Feature: /triage — File-Based Triage Records
  As a developer,
  I want /triage to write a triage record to .triage/<slug>.md
  So that bug investigation output is portable across any issue tracker

  Background:
    Given the agentic-dev-team plugin is installed
    And I am in a project directory

  # ─── Happy path ──────────────────────────────────────────────────────────────

  Scenario: Basic triage creates a .triage/ record
    When I run "/triage 'Login form accepts empty password'"
    And the agent completes its investigation and root cause analysis
    Then a file is written to ".triage/login-form-accepts-empty-password.md"
    And the file contains a Problem section with actual and expected behavior
    And the file contains a Root Cause Analysis section
    And the file contains a TDD Fix Plan with at least one RED/GREEN cycle
    And the file contains an Acceptance Criteria checklist
    And the chat output shows the file path and a one-line root cause summary
    And no GitHub CLI commands are executed

  Scenario: .triage/ directory is created if it does not exist
    Given the .triage/ directory does not exist
    When I run "/triage 'Database connection pool exhausted under load'"
    Then the .triage/ directory is created
    And the triage record is written to ".triage/database-connection-pool-exhausted-under-load.md"

  Scenario: Slug is derived from the bug title
    When I run "/triage 'API returns 500 on /users/:id with special characters (e.g. @, #)'"
    Then the triage record is written to ".triage/api-returns-500-on-users-id-with-special-characters.md"
    And the slug contains only lowercase letters, digits, and hyphens
    And the slug is no longer than 60 characters

  Scenario: Slug collision — record already exists
    Given ".triage/login-returns-401.md" already exists
    When I run "/triage 'Login returns 401'" a second time for a different root cause
    Then the new record is written to ".triage/login-returns-401-2.md"
    And the existing ".triage/login-returns-401.md" is not modified

  Scenario: Triage record includes YAML frontmatter
    When I run "/triage 'Cache invalidation causes stale reads'"
    Then the file ".triage/cache-invalidation-causes-stale-reads.md" begins with YAML frontmatter
    And the frontmatter contains an "id" field matching the slug
    And the frontmatter contains a "created" field with the current date in ISO-8601 format
    And the frontmatter contains a "status: open" field

  Scenario: /explore invokes /triage and receives the file path
    Given /explore detects a critical defect
    When /explore invokes /triage with the probe trace
    Then /triage writes the triage record to ".triage/<slug>.md"
    And /triage outputs the file path in the form "triage-record: .triage/<slug>.md"
    And /explore records the file path in its session report

  # ─── Input handling ───────────────────────────────────────────────────────────

  Scenario: Bug description passed as argument
    When I run "/triage 'Users cannot reset password via email link'"
    Then the agent uses the argument as the starting bug description
    And does not ask for clarification before investigating

  Scenario: No argument provided
    When I run "/triage" with no arguments
    Then the agent asks: "What's the problem you're seeing?"
    And begins investigating immediately after the user responds

  # ─── Error handling ───────────────────────────────────────────────────────────

  Scenario: .triage/ directory is not writable
    Given the .triage/ directory exists but is not writable
    When /triage attempts to write the record
    Then it reports: "Cannot write to .triage/ — check directory permissions"
    And the full triage content is printed to chat so the user can save it manually

  Scenario: Investigation finds no root cause
    When I run "/triage 'Intermittent timeout on CI'"
    And the agent cannot determine a root cause from the available code
    Then a triage record is still written with the investigation findings
    And the Root Cause Analysis section states what was investigated and what was inconclusive
    And the TDD Fix Plan section states "Root cause not determined — manual investigation required"
```

---

## Architecture Specification

### Modified component

| File | Change |
|------|--------|
| `commands/triage.md` | Replace Step 4 (`gh issue create`) with file-write step; update Step 5 to print file path |

No new files required. The `.triage/` directory is a project-level runtime artifact, not a plugin
file.

### `.triage/` file format

```markdown
---
id: <slug>
created: <YYYY-MM-DD>
status: open
---

# <Bug Title>

## Problem

- **Actual behavior**: <what happens>
- **Expected behavior**: <what should happen>
- **Reproduction**: <how to trigger it>

## Root Cause Analysis

<What code path is involved, why it fails, contributing factors.
Describe modules and behaviors, not file paths — the record should
remain useful after refactors.>

## TDD Fix Plan

1. **RED**: Write a test that <expected behavior>
   **GREEN**: <Minimal change to pass>

2. **RED**: Write a test that <next behavior>
   **GREEN**: <Minimal change to pass>

**REFACTOR**: <Any cleanup after all tests pass>

## Acceptance Criteria

- [ ] Root cause is addressed (not just symptom)
- [ ] All new tests pass
- [ ] Existing tests still pass
- [ ] No regressions introduced
```

### Slug algorithm

1. Lowercase the bug title
2. Replace spaces and underscores with hyphens
3. Strip all characters except `[a-z0-9-]`
4. Collapse consecutive hyphens to one
5. Strip leading and trailing hyphens
6. Truncate to 60 characters at a word boundary (do not cut mid-word)

### Collision handling

If `.triage/<slug>.md` exists, append `-2`, `-3`, etc. until a free filename is found. Check
before writing; do not overwrite existing records.

### Return value to callers

After writing the file, the command outputs the file path on a dedicated line so callers such as
`/explore` can parse it:

```
triage-record: .triage/<slug>.md
```

This line appears before the one-line root cause summary in chat output.

### `.triage/` and version control

The command does not add `.triage/` to `.gitignore`. Triage records are project artifacts and
should be committed. Users who want to exclude them manage `.gitignore` themselves.

### GitHub integration

Out of scope. A future `/triage-sync` command or `PostToolUse` hook can read `.triage/*.md` and
call `gh issue create`. This spec does not address that path.

### Downstream dependency closed

The `/explore` spec (`docs/specs/exploratory-testing-explore-command.md`) assumes `/triage`
writes to `.triage/<slug>.md`. This spec fulfils that dependency.

---

## Acceptance Criteria

1. Running `/triage "<description>"` writes a file to `.triage/<slug>.md`; no `gh` CLI commands are executed.
2. The `.triage/` directory is created automatically if absent; the command reports a human-readable error and prints the triage content to chat if the directory is not writable.
3. The slug follows the defined algorithm: lowercase, hyphens, `[a-z0-9-]` only, max 60 characters, no leading/trailing hyphens.
4. If the slug-derived filename already exists, a numeric suffix (`-2`, `-3`) is appended until a free name is found; existing records are never overwritten.
5. The file begins with YAML frontmatter containing `id` (slug), `created` (YYYY-MM-DD), and `status: open`.
6. The file body contains all four sections: Problem, Root Cause Analysis, TDD Fix Plan (at least one RED/GREEN cycle), Acceptance Criteria.
7. When root cause cannot be determined, the record is still written; the TDD Fix Plan section states "Root cause not determined — manual investigation required".
8. After writing, the command prints `triage-record: .triage/<slug>.md` followed by a one-line root cause summary.
9. The investigation workflow (reproduce → investigate → root cause → design fix plan) is unchanged.
10. The updated `triage.md` passes `/agent-audit`.

---

## Consistency Gate

- [x] Intent is unambiguous — two developers would implement to the same observable behavior
- [x] Every behavior in the intent has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering — no new files, no new agents, one command update
- [x] Terminology consistent across all four artifacts — "triage record", "slug", `.triage/`, `status: open`, `triage-record:` prefix
- [x] No contradictions between artifacts
