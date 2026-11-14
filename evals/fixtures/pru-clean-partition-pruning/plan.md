# Plan: Nightly partition pruning for the events table

**Created**: 2026-11-13
**Branch**: chore/prune-event-partitions
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

The `events` table is partitioned by day and grows by about 6 GB a day. The
retention policy is 90 days, but nothing drops old partitions, so disk use is
at 81%. Add a scheduled job that drops partitions older than the retention
window. No API, UI, CLI, or customer-visible behavior changes.

## Acceptance Criteria

- [ ] AC1: The job drops every `events_YYYYMMDD` partition whose date is more than `EVENT_RETENTION_DAYS` (default 90) before the run date.
- [ ] AC2: The job never drops the partition for the run date or any of the previous 90 days.
- [ ] AC3: A second run on the same day drops nothing and exits 0.
- [ ] AC4: Each dropped partition is written to the job log with its name and row count.

## Slices

### Slice 1: Partition pruning job

**Depends-on:** none
**Files:** `jobs/prune_event_partitions.py`, `jobs/schedule.yaml`, `tests/jobs/test_prune_event_partitions.py`

**Behavior:**

```gherkin
Feature: Event partition pruning

  Scenario: Partitions past retention are dropped
    # Still passes if: the log line format changes
    Given partitions for 2026-08-01 and 2026-08-20 exist and the run date is 2026-11-14
    When the pruning job runs with retention 90 days
    Then the 2026-08-01 partition no longer exists
    And the 2026-08-20 partition still exists

  Scenario: Re-run is a no-op
    # Still passes if: the job sleeps 1 second before exiting
    Given the pruning job already ran on 2026-11-14
    When it runs again on 2026-11-14
    Then no partition is dropped and the exit code is 0
```

**Steps:**

#### Step 1.1: Select and drop expired partitions

**Complexity**: standard
**IMPLEMENT**: List `events_*` partitions from the catalog, compute the cutoff, `DROP TABLE` each expired one, log name and row count
**TEST**: Test database with partitions on both sides of the cutoff; assert the exact set dropped; second run drops nothing
**REFACTOR**: Extract `expired(partitions, run_date, days)` as a pure function
**Files**: `jobs/prune_event_partitions.py`, `tests/jobs/test_prune_event_partitions.py`
**Covers**: AC1, AC2, AC3, AC4
**Commit**: `chore(jobs): prune expired event partitions`

#### Step 1.2: Schedule nightly

**Complexity**: trivial
**IMPLEMENT**: Add the job to `jobs/schedule.yaml` at 03:15 UTC
**TEST**: Schedule-config test asserts the entry exists
**REFACTOR**: None
**Files**: `jobs/schedule.yaml`
**Covers**: AC1
**Commit**: `chore(jobs): schedule partition pruning nightly`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Risks & Open Questions

- Dropped partitions cannot be restored except from the nightly backup (kept 14 days); the 90-day window is the documented policy.
