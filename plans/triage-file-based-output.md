# Plan: /triage — File-Based Triage Records

**Created**: 2026-05-08
**Branch**: main
**Status**: draft

## Goal

Replace `/triage`'s GitHub issue creation step with writing a structured markdown file to
`.triage/<slug>.md` in the project root. The investigation workflow is unchanged — only the
output step differs. This makes `/triage` portable across projects that don't use GitHub and
closes the dependency declared by the `/explore` spec.

Spec: `docs/specs/triage-file-based-output.md`

## Acceptance Criteria

- [ ] Running `/triage "<description>"` writes `.triage/<final-slug>.md`; static verification: `grep -r "gh " plugins/dev-team/commands/triage.md` returns nothing
- [ ] `.triage/` is created automatically if absent; if not writable, the command reports "Cannot write to .triage/ — check directory permissions", attempts to write to a system temp path, and prints the full would-be file content (frontmatter + all four body sections) to chat
- [ ] Slug is derived from the bug title using this ordered algorithm: (1) lowercase, (2) strip non-ASCII characters, (3) replace spaces and underscores with hyphens, (4) strip all characters except `[a-z0-9-]`, (5) collapse consecutive hyphens to one, (6) truncate at the last hyphen at or before character 60, (7) strip leading/trailing hyphens, (8) if result is empty use fallback `triage-YYYYMMDD`
- [ ] Slug collision: if `.triage/<slug>.md` exists, append `-2`, `-3`, up to `-99`; existing records are never overwritten; the final resolved filename (not the original slug) is used in the output line
- [ ] File begins with YAML frontmatter: `id` (resolved slug), `created` (YYYY-MM-DD wall-clock date at write time), `status: open`
- [ ] File body contains all four sections: Problem (actual/expected/reproduction), Root Cause Analysis, TDD Fix Plan (≥ 1 RED/GREEN cycle), Acceptance Criteria checklist
- [ ] Root-cause-not-found case: record still written; TDD Fix Plan section body is exactly "Root cause not determined — manual investigation required"
- [ ] After writing, line 1 of output is exactly `triage-record: .triage/<resolved-slug>.md`; line 2 is a single sentence ≤ 120 characters summarising the root cause
- [ ] When invoked without an argument, the agent asks exactly one question ("What's the problem you're seeing?") before investigation begins; when invoked with an argument, no clarifying question is asked
- [ ] `triage.md` passes `/agent-audit`; CLAUDE.md Slash Commands Registry row description and Skills by Phase table entry are updated; no "GitHub" or "gh issue" text remains in the updated sections

## User-Facing Behavior

```gherkin
Feature: /triage — File-Based Triage Records
  As a developer,
  I want /triage to write a triage record to .triage/<slug>.md
  So that bug investigation output is portable across any issue tracker

  Background:
    Given the dev-team plugin is installed
    And I am in a project directory

  Scenario: Basic triage creates a .triage/ record
    When I run "/triage 'Login form accepts empty password'"
    And the agent completes its investigation and root cause analysis
    Then a file is written to ".triage/login-form-accepts-empty-password.md"
    And the file contains a Problem section with actual and expected behavior
    And the file contains a Root Cause Analysis section
    And the file contains a TDD Fix Plan with at least one RED/GREEN cycle
    And the file contains an Acceptance Criteria checklist
    And line 1 of chat output is "triage-record: .triage/login-form-accepts-empty-password.md"
    And line 2 of chat output is a single sentence describing the root cause
    And no gh CLI commands appear in triage.md

  Scenario: .triage/ directory is created if it does not exist
    Given the .triage/ directory does not exist
    When I run "/triage 'Database connection pool exhausted under load'"
    Then the .triage/ directory is created
    And the triage record is written to ".triage/database-connection-pool-exhausted-under-load.md"

  Scenario: Slug derived from title — basic case
    When I run "/triage 'API returns 500 on /users/:id with special characters (e.g. @, #)'"
    Then the triage record is written to ".triage/api-returns-500-on-users-id-with-special-characters.md"
    And the slug contains only lowercase letters, digits, and hyphens
    And the slug is no longer than 60 characters

  Scenario: Slug derived from title — Unicode characters stripped
    When I run "/triage 'Résumé upload causes 400'"
    Then the slug contains only ASCII lowercase letters, digits, and hyphens
    And the triage record filename is ".triage/rsum-upload-causes-400.md"

  Scenario: Slug truncation preserves word boundary
    Given a bug title that produces a raw slug of 68 characters
    And the last hyphen in the first 60 characters is at position 57
    When the slug is computed
    Then the slug is 57 characters long
    And the slug does not end with a hyphen

  Scenario: Empty slug after stripping produces fallback
    When I run "/triage '!!!---!!!'"
    Then the slug fallback matches the pattern "triage-YYYYMMDD"
    And a triage record is written using the fallback slug

  Scenario: Slug collision — resolved filename used in output
    Given ".triage/login-returns-401.md" already exists
    When I run "/triage 'Login returns 401'" for a different root cause
    Then the new record is written to ".triage/login-returns-401-2.md"
    And the existing ".triage/login-returns-401.md" is not modified
    And line 1 of chat output is "triage-record: .triage/login-returns-401-2.md"

  Scenario: Collision chain beyond -2
    Given ".triage/fix-login.md" and ".triage/fix-login-2.md" already exist
    When /triage is invoked with a title generating slug "fix-login"
    Then the new record is written to ".triage/fix-login-3.md"
    And neither ".triage/fix-login.md" nor ".triage/fix-login-2.md" is modified

  Scenario: YAML frontmatter fields
    When I run "/triage 'Cache invalidation causes stale reads'"
    Then the file begins with YAML frontmatter
    And the frontmatter "id" field matches the resolved slug
    And the frontmatter "created" field matches today's date in YYYY-MM-DD format
    And the frontmatter "status" field is "open"

  Scenario: /explore invokes /triage and receives the resolved file path
    Given /explore detects a critical defect
    When /explore invokes /triage with the probe trace
    And a .triage/ collision exists for the initial slug
    Then line 1 of /triage output is "triage-record: .triage/<resolved-slug>.md"
    And /explore records the resolved path in its session report

  Scenario: No argument — one question before investigation
    When I run "/triage" with no arguments
    Then the agent asks exactly: "What's the problem you're seeing?"
    And no investigation steps execute before the user responds
    And no file is written before the user responds

  Scenario: Argument provided — no clarifying question
    When I run "/triage 'Users cannot reset password via email link'"
    Then the agent begins investigating immediately
    And does not ask for clarification

  Scenario: .triage/ not writable — fallback to temp path
    Given the .triage/ directory exists but is not writable
    When /triage attempts to write the record
    Then it reports: "Cannot write to .triage/ — check directory permissions"
    And it attempts to write the file to a system temp path
    And the chat output includes the temp path if write succeeded
    And the full triage content is printed to chat

  Scenario: Investigation finds no root cause
    When I run "/triage 'Intermittent timeout on CI'"
    And the agent cannot determine a root cause from the available code
    Then a triage record is still written
    And the TDD Fix Plan section body is exactly
      "Root cause not determined — manual investigation required"
    And the Root Cause Analysis section describes what was investigated and found inconclusive
```

## Steps

### Step 1: Replace Step 4 and Step 5 in `commands/triage.md`

**Complexity**: standard

**RED**: Establish baseline — confirm the old behavior exists before changing it:

```bash
grep -c "gh issue create" plugins/dev-team/commands/triage.md  # must return 1
grep -c "GitHub" plugins/dev-team/commands/triage.md           # must return >= 1
grep -c "issue URL" plugins/dev-team/commands/triage.md        # record count
```

**GREEN**: Edit `plugins/dev-team/commands/triage.md` with these sub-steps in order:

**1a. Update frontmatter `description`:**

```yaml
description: >-
  Investigate a bug, find its root cause, and write a triage record to
  .triage/<slug>.md with a TDD fix plan. Use when the user reports a bug
  and wants it triaged, says "triage this", "investigate", or wants a
  hands-off bug investigation that produces an actionable record.
```

**1b. Update the intro line** (currently "Investigate a bug hands-off, find root cause, and file
a GitHub issue with a TDD fix plan.") to "Investigate a bug hands-off, find root cause, and write
a triage record to `.triage/<slug>.md` with a TDD fix plan."

**1c. Replace Step 4** entirely with:

```markdown
### 4. Write Triage Record

**Derive the slug** from the bug title using this algorithm (apply in order):

1. Lowercase
2. Strip non-ASCII characters
3. Replace spaces and underscores with hyphens
4. Strip all characters except `[a-z0-9-]`
5. Collapse consecutive hyphens to one
6. Truncate at the last hyphen at or before character 60
7. Strip leading and trailing hyphens
8. If the result is empty, use fallback: `triage-<YYYYMMDD>`

Example: "Fix User Auth (OAuth2 + Résumé)" →
  after step 2: "Fix User Auth (OAuth2 + Rsume)" →
  after step 4: "fix-user-auth-oauth2--rsume" →
  after step 5: "fix-user-auth-oauth2-rsume" (29 chars, no truncation needed)

Example of truncation: a 68-char raw slug with last hyphen at position 57 →
  truncate at position 57 → 57-char slug, no trailing hyphen.

**Check for collision**: if `.triage/<slug>.md` already exists, append `-2`, `-3`, …
up to `-99` until a free filename is found. The final resolved filename is used in all
subsequent steps. Do not overwrite existing records.

**Create directory**:

```bash
mkdir -p .triage/
```

**Handle unwritable directory**: if `.triage/` exists but is not writable, report:
"Cannot write to .triage/ — check directory permissions"
Attempt to write to a system temp file (`/tmp/triage-<slug>-<timestamp>.md` or equivalent).
Report the temp path if the write succeeds. Then print the full would-be file content to chat
(frontmatter + all four body sections) so the user can save it manually.

**Write the file** to `.triage/<resolved-slug>.md`:

```markdown
---
id: <resolved-slug>
created: <YYYY-MM-DD>
status: open
---

# <Bug Title>

## Problem

- **Actual behavior**: [what happens]
- **Expected behavior**: [what should happen]
- **Reproduction**: [how to trigger it]

## Root Cause Analysis

[What code path is involved, why it fails, contributing factors.
Describe modules and behaviors, not file paths — the record should
remain useful after refactors.]

## TDD Fix Plan

1. **RED**: Write a test that [expected behavior]
   **GREEN**: [Minimal change to pass]

**REFACTOR**: [Any cleanup after all tests pass]

## Acceptance Criteria

- [ ] Root cause is addressed (not just symptom)
- [ ] All new tests pass
- [ ] Existing tests still pass
- [ ] No regressions introduced
```

If no root cause was determined, set the TDD Fix Plan body to exactly:
"Root cause not determined — manual investigation required"
```

**1d. Replace Step 5** entirely with:

```markdown
### 5. Present Results

Output two lines — in this order. Line 1 is parsed by callers such as /explore; emit it
only after the final resolved filename is confirmed (collision check complete, file written).

```
triage-record: .triage/<resolved-slug>.md
```

Then print a single sentence (≤ 120 characters) summarising the root cause. Do not repeat
the full record body in chat.
```

**REFACTOR**: Verify no "GitHub", "gh issue", or "issue URL" text remains in the modified
sections. The grep commands from the RED phase confirm this:

```bash
grep "gh " plugins/dev-team/commands/triage.md     # must return nothing
grep "GitHub" plugins/dev-team/commands/triage.md  # must return nothing
```

**Files**: `plugins/dev-team/commands/triage.md`

**Commit**: `feat: write triage records to .triage/ instead of creating GitHub issues`

---

### Step 2: Update CLAUDE.md — two locations

**Complexity**: trivial

**RED**: Confirm both stale locations exist:

```bash
grep "GitHub issue" plugins/dev-team/CLAUDE.md  # must return >= 2 matches
```

**GREEN**:

**Location 1 — Slash Commands Registry table** (search for the `/triage` row):

Old:
```
| `/triage` | `commands/triage.md` | worker | Investigate a bug and file a GitHub issue with TDD fix plan |
```

New:
```
| `/triage` | `commands/triage.md` | worker | Investigate a bug and write a triage record to .triage/<slug>.md with a TDD fix plan |
```

**Location 2 — Skills by Phase table** (search for the `/triage` entry in the Bug Triage row):

Old text: `/triage (Systematic Debugging + GitHub issue creation)`

New text: `/triage (Systematic Debugging + file-based triage record in .triage/)`

**REFACTOR**: Run the RED grep again to confirm both locations updated:

```bash
grep "GitHub issue" plugins/dev-team/CLAUDE.md  # must return nothing
```

**Files**: `plugins/dev-team/CLAUDE.md`

**Commit**: `docs: update /triage registry entries to reflect file-based output`

## Complexity Classification

| Step | Rating | Rationale |
|------|--------|-----------|
| 1: Update triage.md | standard | Behavioral change; introduces slug algorithm, collision handling, directory creation, two new output steps, and temp-write fallback |
| 2: Update CLAUDE.md | trivial | Two description string replacements in registry tables |

## Pre-PR Quality Gate

- [ ] `grep "gh " plugins/dev-team/commands/triage.md` — no matches
- [ ] `grep "GitHub" plugins/dev-team/commands/triage.md` — no matches
- [ ] `grep "GitHub issue" plugins/dev-team/CLAUDE.md` — no matches
- [ ] File format template includes frontmatter with `id`, `created`, `status: open` and all four body sections
- [ ] Step 5 in triage.md emits `triage-record:` line after collision resolution (not before)
- [ ] Slug algorithm steps 1–8 present in correct order with worked examples
- [ ] `/agent-audit` passes with no blockers
- [ ] `/code-review` passes (doc-review, claude-setup-review)

## Risks & Open Questions

- **Breaking change for GitHub users**: existing users who relied on the GitHub issue URL in `/triage` output get no migration path. Consider adding a one-line note on first `.triage/` creation: "To file to GitHub, run: `gh issue create --title '<title>' --body-file .triage/<slug>.md`"
- **Slug truncation word-boundary edge**: if the title is one long word with no hyphens and > 60 chars, step 6 finds no hyphen to truncate at, so the fallback is a hard cut at char 60. Accepted — this is the only viable behavior.
- **/explore caller contract**: the `triage-record:` prefix is a lightweight parsing contract. Stable as long as only `/explore` consumes it; would need formalisation if more callers are added later.

## Plan Review Summary

Four reviewers evaluated this plan. Two required revision (Acceptance Test Critic, UX Critic);
two approved (Design & Architecture Critic, Strategic Critic). All blockers addressed above.

### Acceptance Test Critic — needs-revision → addressed

**Blockers addressed**:
- AC1: static grep verification specified as the testable mechanism for "no gh CLI" assertion
- AC2: "print content to chat" defined as "full would-be file content (frontmatter + four body sections)"; temp-file fallback added
- AC3: full 8-step slug algorithm with source field, Unicode handling, and worked examples
- AC8: output format defined as exactly two lines; line 1 prefix `triage-record:`; line 2 ≤ 120 chars
- AC9: replaced with two specific observable behaviors (argument provided: no question; no argument: exactly one question)

**Warnings accepted**: collision upper bound (-99) noted in AC; date determinism acknowledged (wall-clock, compare with regex in test); /agent-audit criterion split into two observable checks.

### UX Critic — needs-revision → addressed

**Blocker addressed**: collision resolution now explicitly happens before the output line is emitted (Step 1d specifies "emit only after final resolved filename is confirmed")

**Warnings incorporated**:
- Temp-file fallback added to unwritable-directory handling
- Description updated in both CLAUDE.md locations (Step 2 now covers Skills by Phase table too)

**Warnings accepted**: next-step hint for .triage/ workflow deferred to a follow-on (breaking the scope constraint); `triage-record:` prefix inline framing noted as a cosmetic improvement but not blocking

### Design & Architecture Critic — approve

**Observations incorporated**:
- Output ordering contract noted inline in new Step 5 ("callers such as /explore parse this line by prefix")
- Worked examples for truncation and collision added to Step 4 slug algorithm

### Strategic Critic — approve

**Observations incorporated**:
- Skills by Phase table added to Step 2 scope (second stale CLAUDE.md location)
- Breaking change note added to Risks section with suggested migration one-liner
