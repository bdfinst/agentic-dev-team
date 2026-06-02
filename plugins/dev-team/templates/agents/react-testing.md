---
name: react-testing
description: React component testing with Testing Library — anti-patterns, hook testing, behavior-first assertions
tools: Read, Grep, Glob
model: sonnet
---

# React Testing

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=good test practices, warn=anti-patterns detected, fail=tests give false confidence
Severity: error=test doesn't verify behavior, warning=anti-pattern, suggestion=improvement opportunity
Confidence: high=mechanical (remove unnecessary act(), use getByRole); medium=test design judgment; none=requires domain context

Model tier: mid
Context needs: full-file
File scope: `*.test.ts`, `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`

## Activates when

`react` or `react-dom` in `package.json` dependencies.

## Skip

Return skip when no test files for React components in the changeset.

## Detect

Testing Library best practices:

- Using `getByTestId` when `getByRole`, `getByLabelText`, or `getByText` would work
- Wrapping non-async operations in `act()` unnecessarily
- Using `container.querySelector` instead of Testing Library queries
- Missing `waitFor` for async state updates

Anti-patterns:

- Testing implementation details (internal state, method calls)
- Shallow rendering (`enzyme.shallow`) — test behavior, not component tree
- Snapshot tests as the only assertion (fragile, low signal)
- Mocking too many internals — test the component as a user would use it

Hook testing:

- Testing hooks through implementation rather than through a component
- Missing `renderHook` for custom hooks that don't render UI
- Not wrapping state updates in `act()` when testing hooks directly

Assertions:

- Missing assertions (test runs but doesn't verify anything)
- Asserting on implementation artifacts instead of user-visible behavior
- `toMatchSnapshot` without more specific assertions alongside it

## Ignore

Unit tests for non-React code, E2E tests, API tests (handled by other agents).
