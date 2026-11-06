# Plan: Add a doctor command to diagnose an installation

**Created**: 2026-11-04
**Branch**: issue-9002
**Status**: approved
**Gherkin persistence**: plan-file-only
**Spec**: https://example.test/issues/9002

## Goal

One read-only command runs deterministic checks over the installed plugin and
reports each as ok, warn or fail with the command that repairs it.

## Approach stances (decision-defaults)

- **Scope**: the new script, its library module and one skill.

## Design decisions

1. **Isolation.** A check that raises does not take down the report.
2. **Exit codes.** 0 when overall is ok or warn, 1 when fail, 2 on a usage error.

## Acceptance Criteria

- [ ] AC1 The script imports only the standard library.
- [ ] AC2 Each check reports ok, warn or fail with a repair command.
- [ ] AC3 The exit code follows the overall status.

## Slices

### Slice 1: Install-side checks, schema and CLI

**Depends-on:** none
**Files:** `scripts/doctor.py`, `scripts/lib/doctor_report.py`

**Behavior:**

```gherkin
Feature: Install-side checks

  Scenario: A healthy install reports every check ok
    Given a healthy install
    When the doctor runs
    Then every check is ok

  Scenario: A check that raises does not take down the report
    Given a check that raises
    When the doctor runs
    Then the report still lists every other check

  Scenario Outline: The exit code follows the overall status
    Given an overall status of <status>
    When the doctor exits
    Then the exit code is <code>
    Examples:
      | status | code |
      | ok     | 0    |
      | warn   | 0    |
      | fail   | 1    |
```

**Steps:**

#### Step 1.1: Check and report model

**Complexity**: standard
**IMPLEMENT**: A check result type and per-check isolation.
**TEST**: Table-driven result cases.
**Files**: `scripts/lib/doctor_report.py`
**Commit**: `feat(doctor): add the report model`

#### Step 1.2: CLI and exit codes

**Complexity**: standard
**IMPLEMENT**: Argument parsing and the exit-code rule.
**TEST**: One case per exit code.
**Files**: `scripts/doctor.py`
**Commit**: `feat(doctor): add the CLI`

### Slice 2: Project-side checks and the fix flag

**Depends-on:** 1
**Files:** `scripts/doctor.py`

**Behavior:**

```gherkin
Feature: Project-side checks

  Scenario: The metrics directory is missing
    Given a project with no metrics directory
    When the doctor runs
    Then the check warns and names the repair command

  Scenario: The fix flag creates only the two runtime directories
    Given a project with neither directory
    When the doctor runs with the fix flag
    Then both directories exist and nothing else changed
```

**Steps:**

#### Step 2.1: Metrics-writable check

**Complexity**: standard
**IMPLEMENT**: Probe the directory for write access.
**TEST**: Missing, denied and writable cases.
**Files**: `scripts/doctor.py`
**Commit**: `feat(doctor): check the metrics directory`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

## Plan Review Summary

Plan tier: standard - reviewers: Acceptance, Design, Parallelization.

## Approval

Auto-approved (non-interactive) at 2026-11-04 - no human review gate.

## Build Progress

### Slices (grouped by wave)

#### Wave 1
- [ ] Slice 1: Install-side checks, schema and CLI
  - [ ] Step 1.1: Check and report model
  - [ ] Step 1.2: CLI and exit codes

#### Wave 2
- [ ] Slice 2: Project-side checks and the fix flag
  - [ ] Step 2.1: Metrics-writable check
