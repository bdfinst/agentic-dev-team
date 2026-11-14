# Plan: Delete a project from settings

**Created**: 2026-11-12
**Branch**: feat/delete-project
**Status**: draft
**Gherkin persistence**: plan-file-only

## Goal

Workspace owners cannot remove old projects; they ask support to do it (60
requests last quarter). Add a self-serve delete on the project settings page.

## Acceptance Criteria

- [ ] AC1: The project settings page has a "Delete project" button visible only to workspace owners.
- [ ] AC2: Deleting a project removes it, its boards, and its attachments permanently, and returns the owner to the workspace dashboard.
- [ ] AC3: If deletion fails, an error is shown.
- [ ] AC4: Non-owners never see the button and get 403 from the API.

## Slices

### Slice 1: Delete project

**Depends-on:** none
**Files:** `web/src/settings/ProjectSettings.tsx`, `web/src/settings/DeleteProjectButton.tsx`, `web/src/settings/DeleteProjectButton.test.tsx`, `api/projects/delete.ts`, `api/projects/delete.test.ts`

**Behavior:**

```gherkin
Feature: Delete project

  Scenario: Owner deletes a project
    # Still passes if: the dashboard is scrolled to the top after redirect
    Given owner "dana" is on the settings page of project "Website 2024"
    When "dana" clicks "Delete project"
    Then project "Website 2024" no longer exists
    And "dana" is on the workspace dashboard

  Scenario: Deletion fails
    # Still passes if: the error is logged with a different severity
    Given owner "dana" is on the settings page of project "Website 2024"
    And the server cannot delete the project
    When "dana" clicks "Delete project"
    Then an error is shown

  Scenario: Non-owner
    # Still passes if: the 403 body wording changes
    Given member "lee" is on the settings page of project "Website 2024"
    Then no "Delete project" button is shown
```

**Steps:**

#### Step 1.1: API endpoint

**Complexity**: standard
**IMPLEMENT**: `DELETE /projects/:id` for owners; hard-deletes boards and attachments in one transaction; 403 for others
**TEST**: Owner 204 and rows gone; member 403 and rows intact
**REFACTOR**: Reuse `requireOwner`
**Files**: `api/projects/delete.ts`, `api/projects/delete.test.ts`
**Covers**: AC2, AC4
**Commit**: `feat(api): delete project`

#### Step 1.2: Delete button

**Complexity**: standard
**IMPLEMENT**: Red `DeleteProjectButton` in the settings page footer; on click, call `DELETE /projects/:id` immediately and navigate to the dashboard on success; on failure, show an error
**TEST**: Owner sees the button; click calls the API and navigates; failure shows an error
**REFACTOR**: Extract the API call into `projectsApi.remove`
**Files**: `web/src/settings/ProjectSettings.tsx`, `web/src/settings/DeleteProjectButton.tsx`, `web/src/settings/DeleteProjectButton.test.tsx`
**Covers**: AC1, AC2, AC3
**Commit**: `feat(web): add delete project button`

## Parallelization

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] `/code-review` passes
