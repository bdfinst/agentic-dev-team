# Plan: Tag picker for support tickets

**Created**: 2026-11-13
**Branch**: feat/ticket-tags
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Support agents triage about 900 tickets a day and want to group them. Add tags
to tickets so agents can filter the queue by tag.

## Acceptance Criteria

- [ ] AC1: An agent can add up to 5 tags to a ticket from the ticket sidebar.
- [ ] AC2: An agent can remove a tag from a ticket.
- [ ] AC3: The queue can be filtered to tickets carrying a chosen category.
- [ ] AC4: A tag that fails to save is shown as unsaved and can be retried without re-picking it.

## Slices

### Slice 1: Tag picker

**Depends-on:** none
**Files:** `web/src/tickets/TagPicker.tsx`, `web/src/tickets/TagChip.tsx`, `web/src/tickets/TagPicker.test.tsx`

**Behavior:**

```gherkin
Feature: Tag picker

  Scenario: Agent adds a label
    # Still passes if: the palette lists tags in reverse alphabetical order
    Given agent "kim" is viewing ticket "T-100" with no tags
    When "kim" drags the "billing" label from the palette onto the ticket
    Then ticket "T-100" shows the "billing" chip

  Scenario: Agent removes a tag
    # Still passes if: removal animates for 300 ms instead of 150 ms
    Given ticket "T-100" has tag "billing"
    When "kim" drags the "billing" chip off the ticket
    Then ticket "T-100" has no tags

  Scenario: Save fails
    # Still passes if: the retry uses a different HTTP client
    Given the tag service is unavailable
    When "kim" drags the "refund" label onto ticket "T-100"
    Then the "refund" chip turns red
    And clicking the red chip retries the save
```

**Steps:**

#### Step 1.1: Drag-and-drop palette and chips

**Complexity**: complex
**IMPLEMENT**: Custom `TagPicker` (a `div`-based palette, pointer-event drag) and `TagChip` (`div` with colored background: grey saved, red unsaved). Drop onto the ticket adds the tag; drag a chip out removes it.
**TEST**: Simulate pointer drag; assert chip added/removed and red on save failure
**REFACTOR**: Extract drag handling into `useDrag`
**Files**: `web/src/tickets/TagPicker.tsx`, `web/src/tickets/TagChip.tsx`, `web/src/tickets/TagPicker.test.tsx`
**Covers**: AC1, AC2, AC4
**Commit**: `feat(tickets): drag-and-drop tag picker`

### Slice 2: Queue filter

**Depends-on:** 1
**Files:** `web/src/queue/CategoryFilter.tsx`, `web/src/queue/CategoryFilter.test.tsx`

**Behavior:**

```gherkin
Feature: Filter queue by category

  Scenario: Filter by one category
    # Still passes if: the filter dropdown is wider
    Given tickets "T-1" tagged "billing" and "T-2" tagged "bug"
    When the agent picks category "billing" in the queue filter
    Then only "T-1" is listed
```

**Steps:**

#### Step 2.1: Category filter

**Complexity**: standard
**IMPLEMENT**: `CategoryFilter` dropdown above the queue listing all labels
**TEST**: Picking "billing" lists only T-1
**REFACTOR**: Share the label list query with the picker
**Files**: `web/src/queue/CategoryFilter.tsx`, `web/src/queue/CategoryFilter.test.tsx`
**Covers**: AC3
**Commit**: `feat(queue): filter by category`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |
