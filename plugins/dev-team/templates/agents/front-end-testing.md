---
name: front-end-testing
description: Behavior-driven UI testing — query priority, browser-mode preference, HTTP interceptors, framework-agnostic
tools: Read, Grep, Glob
model: sonnet
---

# Front-End Testing

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=good testing practices, warn=anti-patterns, fail=tests unreliable or untestable
Severity: error=unreliable test pattern, warning=anti-pattern, suggestion=improvement
Confidence: high=mechanical (fix query priority); medium=test design; none=requires domain context

Model tier: mid
Context needs: full-file
File scope: `*.test.ts`, `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`, `*.test.js`, `*.test.jsx`

## Activates when

Any frontend framework detected (React, Vue, Svelte, Angular).

## Skip

Return skip when no frontend test files in the changeset.

## Detect

Query priority (most to least preferred):

1. `getByRole` — accessible queries first
2. `getByLabelText` — form fields
3. `getByPlaceholderText` — fallback for unlabeled inputs
4. `getByText` — visible text content
5. `getByDisplayValue` — current form values
6. `getByAltText` — images
7. `getByTitle` — title attributes
8. `getByTestId` — last resort only

Flag violations of this priority order.

Browser-mode preference:

- Prefer Vitest browser mode or Playwright component testing over jsdom
- Flag tests that depend on jsdom quirks (layout, intersection observer, etc.)

HTTP interceptors:

- Prefer MSW (Mock Service Worker) over manual fetch/XHR mocking
- Flag direct `jest.mock` of fetch/axios — use interceptors for realistic testing
- For Angular: prefer `HttpClientTestingModule` over manual spy injection

Behavior-driven:

- Tests should describe user behavior, not component internals
- Test names should read as scenarios ("when user clicks submit, form data is sent")
- Avoid testing CSS classes, internal state, or lifecycle methods directly

## Ignore

Backend tests, E2E/integration tests, non-UI unit tests.
