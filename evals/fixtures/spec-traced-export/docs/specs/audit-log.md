# Spec: Audit log

## Acceptance criteria

1. Every role change records an audit entry with the actor, the target user,
   the old role, the new role, and the time.
2. Audit entries cannot be edited or deleted through the service API.
3. An admin can export the audit log as CSV, one row per entry, oldest first,
   with a header row `time,actor,target,from,to`.
4. A non-admin export request is refused.

## Scenarios

```gherkin
Scenario: Admin exports the audit log
  Given two role changes were recorded
  When an admin exports the audit log
  Then the CSV has a header row and two entry rows, oldest first

Scenario: Viewer cannot export
  Given a user with the viewer role
  When they request the audit log export
  Then the request is refused
```

## Plan — files to change

- `src/audit-log.ts` — record entries and export CSV for admins.
- `tests/audit-log.test.ts` — cover all four criteria and both scenarios.
