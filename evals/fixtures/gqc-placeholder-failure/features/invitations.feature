# Derived from: src/routes/invitations.ts  POST /workspaces/:workspaceId/invitations
Feature: Invite a person to a workspace

  Background:
    Given workspace "W-1" exists
    And "ana@example.com" is an admin of "W-1"

  Scenario: Admin invites a new member
    Given "ana@example.com" is signed in
    When she invites "bo@example.com" to "W-1"
    Then the response status is 201
    And an invitation for "bo@example.com" with role "member" exists

  Scenario: Admin invites a new admin
    Given "ana@example.com" is signed in
    When she invites "cy@example.com" to "W-1" with role "admin"
    Then the response status is 201
    And an invitation for "cy@example.com" with role "admin" exists

  Scenario: Admin invites with a personal message
    Given "ana@example.com" is signed in
    When she invites "di@example.com" to "W-1" with message "Welcome aboard"
    Then the response status is 201
    And the invitation for "di@example.com" carries message "Welcome aboard"

  Scenario: Invalid request is rejected
    Given <invalid request>
    When the invitation is submitted
    Then <failure-mode-summary>
