# Plan: a slice with a scenario and no step

**Created**: 2026-01-02
**Branch**: issue-1
**Status**: approved
**Spec**: https://example.test/issues/1

## Goal

Parse the input and build the output.

## Acceptance Criteria

- [ ] AC1 The parser reads the input
- [ ] AC2 The builder writes the output

## Slices

### Slice 1: Parse

**Depends-on:** none
**Files:** `src/parse.py`, `tests/test_parse.py`

**Behavior:**

```gherkin
Feature: Parse

  Scenario: the parser reads a line
    Given a line
    When it is parsed
    Then it has a token
```

**Steps:**

#### Step 1.1: Parse a line

**IMPLEMENT**: Write the parser
**TEST**: Parse a line
**Files**: `src/parse.py`
**Commit**: `feat: parse a line`

### Slice 2: Build

**Depends-on:** 1
**Files:** `src/build.py`, `tests/test_build.py`

**Behavior:**

```gherkin
Feature: Build

  Scenario: the builder writes a file
    Given a token
    When it is built
    Then a file exists

  Scenario Outline: the builder handles sizes
    Given a <size>
    When it is built
    Then it is written
    Examples:
      | size  |
      | small |
```

**Steps:**

## Build Progress

### Slices

- [x] Slice 1: Parse
  - [x] Step 1.1: Parse a line
- [ ] Slice 2: Build
