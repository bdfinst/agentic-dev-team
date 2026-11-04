# Plan: One missing falsifier

**Created**: 2026-11-04
**Status**: approved

## Goal

The last scenario lacks a falsifier.

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
    Then it works

  Scenario: Beta works
    # Still passes if: the title is reworded
    Given a beta
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

  Scenario: Gamma works
    Given a gamma
    Then it works
```

**Steps:**

#### Step 2.1: Gamma

**Commit**: `feat: gamma`
