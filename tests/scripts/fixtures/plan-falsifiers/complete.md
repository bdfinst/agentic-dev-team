# Plan: Complete falsifiers

**Created**: 2026-11-04
**Status**: approved

## Goal

Every scenario carries a falsifier.

## Slices

### Slice 1: First slice

**Depends-on:** none
**Files:** `a.py`

**Behavior:**

```gherkin
Feature: First

  Scenario: Alpha works
    # Still passes if: the key order changes
    Given an alpha
    When it runs
    Then it works
```

**Steps:**

#### Step 1.1: Alpha

**Commit**: `feat: alpha`

### Slice 2: Second slice

**Depends-on:** 1
**Files:** `b.py`

**Behavior:**

```gherkin
Feature: Second

  Scenario Outline: Beta handles <kind>
    # Still passes if: the Examples table gains a row
    Given a <kind> beta
    Then it is handled

    Examples:
      | kind |
      | big  |
```

**Steps:**

#### Step 2.1: Beta

**Commit**: `feat: beta`
