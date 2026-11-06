# Plan: seeded-defect CLI (acceptance-examiner live check)

**Status**: implemented

This fixture exists for the acceptance examiner's seeded-defect check: its tests pass against the wrong output, and only running the command shows the defect.

## Acceptance Criteria

- [ ] AC1 `python3 tests/scripts/fixtures/seeded-cli/cli.py 4 6` prints `sum=10`. Observe: `python3 tests/scripts/fixtures/seeded-cli/cli.py 4 6` prints exactly `sum=10`.

## Slices

### Slice 1: Sum CLI

```gherkin
Feature: Sum CLI

  Scenario: The CLI prints the sum of its arguments
    Given the arguments "4" and "6"
    When the CLI runs
    Then it prints "sum=10"
```

## Pre-PR Quality Gate

- [ ] Tests pass: `python3 -m pytest tests/scripts/fixtures/seeded-cli -q`

## Build Progress

- [x] Slice 1: Sum CLI
