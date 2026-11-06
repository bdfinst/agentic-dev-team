# Plan: Source-blind examiner after the build

**Created**: 2026-11-04
**Branch**: issue-9001
**Status**: approved
**Gherkin persistence**: plan-file-only
**Spec**: https://example.test/issues/9001
**Revision**: 3

## Problem

The build reports done without anyone checking the criteria against the result.

## Goal

Add an examiner that checks each acceptance criterion against the built result
and records one verdict per criterion.

## Approach stances (decision-defaults)

- **Scope**: only the files named in the Slices.
- **Failure mode**: fail open; a parser bug never blocks a write.

## Design decisions (carried from plan review, rounds 1-3)

1. **Record shape.** One row per criterion with `verdict` in {met, not-met}.
2. **Binding.** The record carries the branch-diff hash; the plan file is excluded.

## Acceptance Criteria

- [ ] AC1 The examiner agent exists and is registered.
- [ ] AC2 The build skill runs the examiner between Step 7 and Step 7.5.
- [ ] AC3 The record has one row per plan criterion.

## Slices

### Slice 1: Examination record and gate

**Depends-on:** none
**Files:** `scripts/examination.py`, `tests/test_examination.py`

**Behavior:**

```gherkin
Feature: Examination record

  Scenario Outline: Criteria boundary shapes
    Given a plan with <criteria>
    When the record is built
    Then it has <rows> rows
    Examples:
      | criteria | rows |
      | none     | 0    |
      | two      | 2    |

  Scenario: A complete met result derives an overall met
    Given every row is met
    When the verdict is derived
    Then the overall verdict is met
```

**Steps:**

#### Step 1.1: Record model

**Complexity**: standard
**IMPLEMENT**: Build the record from the plan criteria.
**TEST**: Table-driven boundary cases.
**Files**: `scripts/examination.py`, `tests/test_examination.py`
**Covers**: AC3
**Commit**: `feat(examination): add the record model`

#### Step 1.2: Gate

**Complexity**: complex
**IMPLEMENT**: Refuse a stale or missing record.
**TEST**: One case per refusal.
**Files**: `scripts/examination.py`, `tests/test_examination.py`
**Covers**: AC3
**Commit**: `feat(examination): gate on the record`

### Slice 2: Agent and skill step

**Depends-on:** 1
**Files:** `agents/examiner.md`, `skills/build/SKILL.md`

**Behavior:**

```gherkin
Feature: Examiner wiring

  Scenario: The agent is registered
    Given the registry
    When it is read
    Then the examiner has a row

  Scenario: The build skill dispatches the examiner
    Given the build skill
    When Step 7.6 is read
    Then it sits between Step 7 and Step 7.5
```

**Steps:**

#### Step 2.1: Agent and registry rows

**Complexity**: trivial
**IMPLEMENT**: Add the agent file and its registry rows.
**TEST**: The registry gate stays green.
**Files**: `agents/examiner.md`
**Covers**: AC1
**Commit**: `feat(agents): add the examiner`

#### Step 2.2: Build skill step

**Complexity**: standard
**IMPLEMENT**: Add Step 7.6.
**TEST**: Prose-contract test pins the order.
**Files**: `skills/build/SKILL.md`
**Covers**: AC2
**Commit**: `feat(build): dispatch the examiner`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] Linter passes

## Plan Review Summary

Plan tier: standard - reviewers: Acceptance, Design.

- **Acceptance** (iterations 1-3): iteration 1 blocker fixed in revision 2.
- **Design** (iterations 1-3): approve.

## Approval

Auto-approved (non-interactive) at 2026-11-04 - no human review gate.

## Build Progress

This section is the machine-parseable recovery handle.

### Acceptance Criteria

- [ ] AC1 The examiner agent exists and is registered.
- [ ] AC2 The build skill runs the examiner between Step 7 and Step 7.5.
- [ ] AC3 The record has one row per plan criterion.

### Slices (grouped by wave)

#### Wave 1
- [x] Slice 1: Examination record and gate
  - [x] Step 1.1: Record model
  - [x] Step 1.2: Gate

#### Wave 2
- [ ] Slice 2: Agent and skill step
  - [ ] Step 2.1: Agent and registry rows
  - [ ] Step 2.2: Build skill step
