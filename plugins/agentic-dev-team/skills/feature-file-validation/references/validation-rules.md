# Feature File Validation — Detailed Rules

## Gherkin Syntax Checks

- Every scenario has at least one `Given`, one `When`, and one `Then` step
- `Background` sections contain only `Given` steps (setup, not actions)
- `Scenario Outline` uses `Examples` tables with at least one row
- No orphan steps outside a `Scenario`, `Scenario Outline`, or `Background`
- Feature has a descriptive name (not blank or generic like "Test" or "Feature 1")

## Determinism Patterns

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

## Implementation Independence Patterns

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

## Scenario Quality Checks

- **Single behavior per scenario** — flag scenarios with more than one `When`
  step (unless using `And` to describe a multi-part action that is logically
  one behavior).
- **Vague assertions** — `Then it works`, `Then the operation succeeds`,
  `Then no errors occur`. Assertions should describe observable outcomes.
- **Missing negative cases** — if a feature only has happy-path scenarios,
  suggest adding error/edge case scenarios (as a suggestion, not an error).

## Framework Detection — Step Definition Location Patterns

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

## Coverage Strategies

### Strategy A: Step Definition Matching

For each `Given`/`When`/`Then` step in the scenario, search for a step
definition whose regex or string pattern matches the step text. A scenario is
covered when all its steps have matching definitions. Use the framework
detection table above to locate step definition files.

### Strategy B: Test File Naming Convention

Look for test files whose name corresponds to the feature file:

- `login.feature` -> `login.test.ts`, `login.spec.js`, `test_login.py`,
  `LoginTest.java`, `LoginTests.cs`, `login_test.go`
- Check both the same directory and common test directory patterns
  (`test/`, `tests/`, `spec/`, `__tests__/`, `src/test/`)

A scenario is covered if the corresponding test file exists AND contains a
test or describe block that references the scenario name or a close
paraphrase.

## Severity Mapping

| Category | Severity | Rationale |
|----------|----------|-----------|
| Missing step definitions for all steps | error | Scenario is untested — a broken promise |
| Non-deterministic scenario | error | Produces flaky tests that erode trust |
| Implementation-coupled steps | warning | Makes scenarios brittle to refactoring |
| Missing Given/When/Then structure | warning | Likely incomplete scenario |
| Vague assertions | warning | Weak regression protection |
| Missing negative scenarios | suggestion | Improved coverage opportunity |
| Partial step coverage | warning | Some steps untested |

## Confidence Mapping

| Pattern | Confidence |
|---------|-----------|
| Step text contains `Date.now`, SQL, or class names | high |
| Step references "today" or "current time" | high |
| No step definition file found anywhere in project | high |
| Step text mentions a technology by name | medium |
| Scenario has only happy paths | none (subjective) |
