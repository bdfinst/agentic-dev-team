---
name: gherkin-public
description: >-
  Author Gherkin scenarios for the entire public interface of a repository
  — every API endpoint, UI screen, batch-job entry point, library export,
  and event type — at the observable boundary, not internal steps. The
  scenarios become the executable specification of intended behavior before
  any test or production-code change lands. After the operator approves the
  scenarios at the Phase-2 gate, this skill also creates the Phase-4 and
  Phase-5 `[Component tests]` Stories that will bind their test code to
  specific scenario names — so the component tests are written from the
  approved Gherkin, not from the assessment.
argument-hint: "<repo-path> [--repo-slug <slug>] [--parent <issue-url>] [--create-stories]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Gherkin Public

Role: worker. Phase-2 of `/test-modernize`. Reads the component map produced by `/cd-test-architecture` and writes `.feature` files at the **public boundary** of each component — the surface an external caller actually depends on. Internal steps are out of scope here; scenarios describe observable outputs.

You have been invoked with the `/gherkin-public` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>` — the repo under modernization.
- `--repo-slug <slug>` — namespace under `memory/test-modernize/`. Defaults to the last path segment of `<repo-path>`.

If `<repo-path>` is absent, ask the operator.

## Steps

### 1. Load the component map

Read `memory/test-modernize/<slug>/phase-1.md` for the components & patterns table. If it's missing, tell the operator Phase 1 has not run and stop.

### 2. Pick the output directory

- Prefer `features/test-modernize/` if `<repo>/features/` already exists (matches the repo's existing Gherkin layout).
- Otherwise write to `<repo>/specs/test-modernize/`.
- Create the directory if missing.

### 3. Author scenarios per public surface

For each component in the map, generate one `.feature` file per public surface using the pattern's template. Every scenario MUST cover at least one success and one failure path. Every scenario MUST be observable at the boundary — no scenario describes an internal call.

**API Provider** (one `.feature` per endpoint):

```gherkin
Feature: <method> <path>
  As an external API consumer
  I want <documented behavior>
  So that <user value>

  Scenario: <success-path-summary>
    Given <request shape + auth context>
    When the client calls <method> <path>
    Then the response status is <code>
    And the body conforms to <schema reference>

  Scenario: <failure-mode-summary, per the assessment's failure-modes list>
    Given <invalid request>
    When the client calls <method> <path>
    Then the response status is <code>
    And the error body includes <field>
```

**User Interface** (one `.feature` per user-facing flow):

```gherkin
Feature: <flow name>
  As a <user role>
  I want <task>
  So that <outcome>

  Scenario: <happy path>
    Given <starting screen + preconditions>
    When the user <observable action sequence>
    Then the user sees <observable outcome>
    And the URL is <route> (or app state is <state>)

  Scenario: <validation / error path>
    Given <invalid input>
    When the user submits
    Then the user sees <error message>
    And no destructive change has occurred
```

**Batch / Scheduled Job** (one `.feature` per job; the entry point is the surface):

```gherkin
Feature: <job name> — scheduled entry point

  Scenario: <success path — full input → expected outputs>
    Given the input source contains <fixture rows / messages>
    When the job is triggered at its scheduled entry point
    Then the job exits with code 0
    And the output sink contains <expected rows / files / events>
    And the run-metrics show <count> processed

  Scenario: <partial-failure path>
    Given the input source contains <N valid + M invalid rows>
    When the job is triggered
    Then the job exits with code <non-zero per the contract, or 0 with reported errors>
    And the dead-letter sink contains the M invalid rows
    And no valid row was dropped
```

**CLI / Library** (one `.feature` per command or exported function):

```gherkin
Feature: <command-or-function>

  Scenario: <documented success>
    Given <preconditions / stdin / args>
    When the caller invokes <cmd-or-fn> with <args>
    Then the exit code is <n> (or the return value is <shape>)
    And stdout contains <pattern>

  Scenario: <documented error>
    Given <invalid input>
    When the caller invokes <cmd-or-fn>
    Then the exit code is <non-zero>
    And stderr contains <message>
```

**API / Event Consumer** (one `.feature` per outbound call or emitted event):

```gherkin
Feature: <component> emits <event-type>

  Scenario: <triggering input → expected emission>
    Given <inbound trigger>
    When the component processes it
    Then an event of type <type> is emitted to <sink>
    And the event body matches <schema>
```

**Event Producer / Stateful Service** — combine the API Provider and Event Consumer templates as appropriate.

### 4. Cite the assessment

In every `.feature` file's header, include:

```
# Source: memory/test-modernize/<slug>/phase-1.md
# Component: <name>
# Pattern: <pattern>
# Public surface: <surface-id>
```

This lets the gate-keeper review agent (`dev-team:test-modernization-review`) trace each scenario back to a component row.

### 5. Persist phase-2 progress

Write `memory/test-modernize/<slug>/phase-2.md` with:

- Number of `.feature` files written + their paths.
- Surface coverage per component (one row per component: surfaces touched / surfaces total).
- Any components for which the operator must hand-author scenarios (e.g. heavy UI flows the worker could not derive from the map alone) — call these out explicitly.
- The scenario inventory: per component, the full list of `<feature-file>::<scenario-name>` pairs.

### 6. STOP for human sign-off

This is the Phase-2 human gate the orchestrator (`/test-modernize`) enforces. Print the scenario inventory and wait. Do NOT proceed to Step 7 (Story creation) until the operator signs off on the scenarios. The Gherkin is the executable spec — Stories that bind to it must not be created from un-reviewed scenarios.

### 7. Create `[Component tests]` Stories bound to the approved scenarios

Once the operator has approved the scenarios (orchestrator passes `--create-stories` or `/gherkin-public` is re-invoked after approval), create one `[Component tests]` Story per (component, surface) pair via the resolved tracker CLI from Phase 0:

- **Title:** `[Component tests] <component> · <surface-id>` (e.g. `[Component tests] orders-api · POST /orders`).
- **Phase tag:** `Phase-4` when the surface is fully reachable at existing seams (per the seam-reachability table in `phase-1.md`); `Phase-5` when one or more scenarios require a `[Refactor-for-testability]` Story.
- **Predecessor links:**
  - `[Baseline]` for the same component (from Phase 1) — baseline before tests.
  - For Phase-5 Stories, also the matching `[Refactor-for-testability]` Story for any scenario that requires the refactor.
- **Body — Acceptance Criteria (this is the binding):**

  ```markdown
  ## Approved Gherkin scenarios (binding contract)

  All scenarios below MUST have a passing test in this Story. Each test:
  - cites the source `.feature` file + scenario name in its name or a leading comment;
  - exercises the scenario via the public surface (no internal-step assertions);
  - runs deterministically with no off-machine dependencies (airplane test);
  - lands at the **component** layer per the MinimumCD taxonomy.

  Source: `features/test-modernize/<surface>.feature`

  - [ ] `Scenario: <success-path-summary>`
  - [ ] `Scenario: <failure-mode-summary>`
  - [ ] `Scenario: <…>`

  ## Testing approach

  Binding mode: `<bdd-runner | xunit-with-annotations>` (from Phase 0).

  - `bdd-runner` — generate step definitions for the scenarios above using the project's BDD runner (cucumber-js / pytest-bdd / behave / cucumber-jvm / SpecFlow / godog). Step definitions go under the project's existing step-defs directory.
  - `xunit-with-annotations` — write one xUnit-style test method per scenario. The test method name SHALL mirror the scenario name (e.g. `Scenario: rejects invalid total` → `test_rejects_invalid_total()` / `RejectsInvalidTotal()` / etc.). The Given / When / Then become structured comments at the top of each test body, citing the feature file path.

  ## Doubles

  <In-memory doubles for third-party dependencies + local containers / loopback for team-owned infrastructure. No off-machine calls.>
  ```

Record the **scenario → Story-id** map in `memory/test-modernize/<slug>/gherkin-bindings.json`:

```json
{
  "features/test-modernize/orders-post.feature::accepts valid order": 311,
  "features/test-modernize/orders-post.feature::rejects invalid total": 311,
  "features/test-modernize/orders-get.feature::returns existing order": 312,
  …
}
```

Append the Story creations to `phase-2.md` (one row per Story: title, phase tag, scenario count, tracker-id, predecessors). The map is the artifact `dev-team:test-modernization-review --phase 2` reads to verify every Scenario has a Story citing it.

### 8. Report

Print:

- Output directory used.
- N `.feature` files written.
- Any components flagged for hand-authoring.
- N `[Component tests]` Stories created with scenario-binding count per Story.
- The phase-2 progress file path and the `gherkin-bindings.json` path.

## Notes

- This skill runs in **two passes**, separated by the Phase-2 human gate:
  1. First pass (Steps 1–6) authors the `.feature` files and stops for sign-off.
  2. Second pass (Step 7), invoked by the orchestrator with `--create-stories` after the operator approves, creates the `[Component tests]` Stories bound to the approved scenarios. Splitting the passes ensures the Stories never reference un-reviewed scenarios.
- The Stories produced here become the binding contract `/build` consumes in Phase 4 and Phase 5. Each Story's body cites the exact scenarios its tests must satisfy — the component tests are written **from the approved Gherkin**, not from the assessment.
- `gherkin-bindings.json` is the inverse map (scenario → Story). `test-modernization-review --phase 2` uses it to verify every Scenario in every `.feature` has a Story citing it; `--phase 4` uses it to verify each `[Component tests]` Story's submitted test code references its scenarios.
- For UI patterns where the worker cannot infer the flow from the assessment alone, emit a stub `.feature` with the required header and a `# TODO: hand-author scenarios here` block — better to surface the gap than to invent steps. Stub `.feature` files do NOT generate Stories until the operator fills them in.
