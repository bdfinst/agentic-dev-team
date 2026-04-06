---
name: feature-file-validation
description: >-
  Validate Gherkin feature files for structural quality, determinism, and
  implementation independence, then verify each scenario has matching test
  automation. Use this skill whenever reviewing test files, feature files, or
  BDD scenarios — including during /code-review when .feature files or step
  definition files appear in the changeset. Also use when a user asks to
  "check my feature files", "validate my Gherkin", "are my scenarios
  testable", or "do my feature files have tests".
role: worker
user-invocable: true
---

# Feature File Validation

## Overview

Feature files are the contract between intent and implementation. When they
contain implementation details, rely on non-deterministic conditions, or lack
corresponding test automation, they undermine the entire ATDD workflow. A
scenario that says "the database INSERT completes in under 50ms" tests
infrastructure, not behavior. A scenario with no step definition is a promise
nobody keeps.

This skill validates two things:
1. **Feature file quality** — are the scenarios well-formed, deterministic,
   and behavioral (not implementation-coupled)?
2. **Test automation coverage** — does every scenario have a matching step
   definition file and/or test file?

## When to Run

- During `/code-review` when `.feature` files or step definition files are in
  the changeset
- When the `test-review` agent encounters feature files in the target
- When a user explicitly asks to validate feature files or BDD scenarios
- Before `/build` starts, as a pre-flight check on spec artifacts

## Step 1: Find Feature Files

Locate all `.feature` files in the target scope. If reviewing changed files
only, limit to `.feature` files in the changeset plus any `.feature` files
referenced by changed step definition files.

If no `.feature` files are found, report skip and stop.

## Step 2: Validate Feature File Structure

For each feature file, check these categories:

### Gherkin syntax

- Every scenario has at least one `Given`, one `When`, and one `Then` step
- `Background` sections contain only `Given` steps (setup, not actions)
- `Scenario Outline` uses `Examples` tables with at least one row
- No orphan steps outside a `Scenario`, `Scenario Outline`, or `Background`
- Feature has a descriptive name (not blank or generic like "Test" or "Feature 1")

### Determinism

Scenarios must produce the same result every time, regardless of when, where,
or in what order they run. Flag these patterns:

- **Time-dependent steps** — references to "today", "now", "current date",
  "within 5 seconds", clock-based assertions. Deterministic alternative: use
  fixed dates ("Given the date is 2024-03-15") or relative descriptions
  ("Given a date 30 days in the past").
- **Order-dependent scenarios** — steps that assume prior scenario state
  ("Given the user created in the previous test"). Each scenario must be
  independently runnable.
- **Environment-dependent steps** — references to specific servers, ports,
  file paths, or environment variables without parameterization.
- **Random or probabilistic assertions** — "should sometimes", "approximately",
  "within a range" without fixed boundaries.
- **Concurrency assumptions** — "when two users simultaneously", "while the
  batch job is running" without controlled synchronization described in the
  scenario.

### Implementation independence

Scenarios describe *what* the system does, not *how* it does it. Flag:

- **Technology references** — database names (PostgreSQL, MongoDB), framework
  names (React, Spring), protocols (REST, gRPC), or infrastructure (Redis,
  Kafka) in step text. These belong in step definitions, not scenarios.
- **Code-level details** — class names, method names, variable names, SQL
  statements, API paths (`/api/v1/users`), HTTP methods, or status codes in
  step text.
- **UI implementation details** — CSS selectors, element IDs, pixel
  coordinates, or specific UI framework components. Acceptable: "the user
  clicks the submit button." Not acceptable: "the user clicks `#btn-submit`."
- **Performance/timing constraints** — "completes in under 200ms", "returns
  within 5 seconds". These are non-functional requirements that belong in
  separate performance test specs, not behavioral scenarios.
- **Data structure specifics** — JSON schemas, XML structures, column names,
  or internal data formats exposed in step text.

### Scenario quality

- **Single behavior per scenario** — flag scenarios with more than one `When`
  step (unless using `And` to describe a multi-part action that is logically
  one behavior).
- **Vague assertions** — `Then it works`, `Then the operation succeeds`,
  `Then no errors occur`. Assertions should describe observable outcomes.
- **Missing negative cases** — if a feature only has happy-path scenarios,
  suggest adding error/edge case scenarios (as a suggestion, not an error).

## Step 3: Verify Test Automation Coverage

For each scenario, verify that test automation exists. Check using two
strategies and report a match if either succeeds:

### Strategy A: Step definition matching

Look for step definition files that match the step text patterns. Detection
by framework:

| Framework | Step definition location patterns |
|-----------|----------------------------------|
| Cucumber.js | `**/*.steps.{js,ts}`, `**/step_definitions/**/*.{js,ts}`, `**/steps/**/*.{js,ts}` |
| pytest-bdd | `**/conftest.py`, `**/test_*.py`, `**/*_test.py` containing `@given`, `@when`, `@then` |
| SpecFlow (C#) | `**/*Steps.cs`, `**/*StepDefinitions.cs`, `**/Steps/**/*.cs` |
| Cucumber (Java) | `**/*Steps.java`, `**/*StepDefs.java`, `**/steps/**/*.java` containing `@Given`, `@When`, `@Then` |
| Cucumber (Ruby) | `**/step_definitions/**/*.rb` |
| Behave (Python) | `**/steps/**/*.py`, `**/environment.py` |
| Karate | `**/*.feature` files are self-contained (Karate tests are feature files) |
| Go (godog) | `**/*_test.go` containing `godog.Step` or `ScenarioInitializer` |

For each `Given`/`When`/`Then` step in the scenario, search for a step
definition whose regex or string pattern matches the step text. A scenario is
covered when all its steps have matching definitions.

### Strategy B: Test file naming convention

Look for test files whose name corresponds to the feature file:

- `login.feature` → `login.test.ts`, `login.spec.js`, `test_login.py`,
  `LoginTest.java`, `LoginTests.cs`, `login_test.go`
- Check both the same directory and common test directory patterns
  (`test/`, `tests/`, `spec/`, `__tests__/`, `src/test/`)

A scenario is covered if the corresponding test file exists AND contains a
test or describe block that references the scenario name or a close
paraphrase.

### Coverage report

For each feature file, report:
- Total scenarios
- Covered scenarios (step definitions found OR test file match)
- Uncovered scenarios (neither strategy found a match)
- Partially covered scenarios (some steps have definitions, others don't)

## Step 4: Output

Report findings using the standard review agent output format:

```json
{
  "status": "pass|warn|fail",
  "issues": [
    {
      "severity": "error|warning|suggestion",
      "confidence": "high|medium|none",
      "file": "features/login.feature",
      "line": 12,
      "message": "Description of the issue",
      "category": "determinism|implementation-coupling|structure|coverage",
      "suggestedFix": "How to fix it"
    }
  ],
  "coverage": {
    "total_scenarios": 0,
    "covered": 0,
    "uncovered": 0,
    "partial": 0
  },
  "summary": "One-line summary"
}
```

### Severity mapping

| Category | Severity | Rationale |
|----------|----------|-----------|
| Missing step definitions for all steps | error | Scenario is untested — a broken promise |
| Non-deterministic scenario | error | Produces flaky tests that erode trust |
| Implementation-coupled steps | warning | Makes scenarios brittle to refactoring |
| Missing Given/When/Then structure | warning | Likely incomplete scenario |
| Vague assertions | warning | Weak regression protection |
| Missing negative scenarios | suggestion | Improved coverage opportunity |
| Partial step coverage | warning | Some steps untested |

### Confidence mapping

| Pattern | Confidence |
|---------|-----------|
| Step text contains `Date.now`, SQL, or class names | high |
| Step references "today" or "current time" | high |
| No step definition file found anywhere in project | high |
| Step text mentions a technology by name | medium |
| Scenario has only happy paths | none (subjective) |
