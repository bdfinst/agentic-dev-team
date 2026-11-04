# Plan: Open, compose and integrate lanes

**Created**: 2026-11-04
**Branch**: issue-9003
**Status**: approved
**Gherkin persistence**: plan-file-only
**Spec**: docs/specs/lanes/spec.md
**Revision**: 2

## Goal

Run build lanes in isolated worktrees, compose their results, and integrate
the composed result once.

## Terminology

- **lane**: one isolated worktree that builds one wave slice.

## Acceptance Criteria

- [ ] AC1 A lane opens in its own worktree.
- [ ] AC2 Composed lanes integrate once, in plan order.
- [ ] AC3 A failed lane leaves the others intact.
- [ ] A criterion written without an id takes its position.

## Slices

### Slice 1: Open a lane

**Depends-on:** none
**Files:** `scripts/lane.py`

**Behavior:**

```gherkin
Feature: Open a lane

  Scenario: A lane opens in a fresh worktree
    Given a plan with one slice
    When the lane opens
    Then a worktree exists for that slice
```

**Steps:**

#### Step 1.1: Open

**Complexity**: standard
**IMPLEMENT**: Create the worktree. The setup command is shown below.

```bash
# A line that looks like a Covers marker, inside a fence, is not read:
# **Covers**: AC9
git worktree add ../lane-1 -b lane-1
```

**TEST**: The worktree exists after open.
**Files**: `scripts/lane.py`
**Covers**: AC1
**Commit**: `feat(lane): open a lane`

### Slice 2: Compose and integrate

**Depends-on:** 1
**Files:** `scripts/compose.py`

**Behavior:**

```gherkin
Feature: Compose and integrate

  Scenario Outline: Lanes integrate in plan order
    Given <count> lanes
    When they are composed
    Then they integrate in plan order
    Examples:
      | count |
      | 2     |
      | 5     |

  Scenario: A failed lane leaves the others intact
    Given three lanes and one that fails
    When they are composed
    Then the other two are integrated
```

**Steps:**

#### Step 2.1: Compose

**Complexity**: complex
**IMPLEMENT**: Merge lane results in plan order.
**TEST**: Order cases.
**Files**: `scripts/compose.py`
**Covers**: AC2
**Commit**: `feat(lane): compose results`

#### Step 2.2: Isolate failure

**Complexity**: standard
**IMPLEMENT**: A failed lane is dropped from the composition.
**TEST**: One failing lane of three.
**Files**: `scripts/compose.py`
**Covers**: AC3, AC4
**Commit**: `feat(lane): isolate a failed lane`

## Plan Review Summary

Plan tier: complex - reviewers: Acceptance, Design, Strategic.

- **Open blocker**: Slice 2 - the failed-lane path has no scenario
- **Resolved blocker**: Slice 2 - the failed-lane path has no scenario

## Approval

Auto-approved (non-interactive) at 2026-11-04 - no human review gate.

## Build Progress

### Slices (grouped by wave)

#### Wave 1
- [x] Slice 1: Open a lane
  - [x] Step 1.1: Open

#### Wave 2
- [x] Slice 2: Compose and integrate
  - [x] Step 2.1: Compose
  - [x] Step 2.2: Isolate failure
