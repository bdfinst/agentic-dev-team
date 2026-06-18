---
name: gherkin-public
description: >-
  Author Gherkin scenarios for the entire public interface of a repository
  — every API endpoint, UI screen, batch-job entry point, library export,
  and event type — at the observable boundary, not internal steps. The
  scenarios become the executable specification of intended behavior before
  any test or production-code change lands. Pattern-specific scenario
  templates per the component map written by `/cd-test-architecture`.
argument-hint: "<repo-path> [--repo-slug <slug>]"
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

### 6. Report

Print:

- Output directory used.
- N `.feature` files written.
- Any components flagged for hand-authoring.
- The phase-2 progress file path.

## Notes

- Scenarios describe **intent**, not yet a passing test. The validator and the binding to step definitions happen later. Phase 2 is the human-review gate; do not bind scenarios to runners here.
- The orchestrator (`/test-modernize`) holds the human gate after this worker returns. The operator MUST sign off on the scenarios before Phase 3 starts.
- For UI patterns where the worker cannot infer the flow from the assessment alone, emit a stub `.feature` with the required header and a `# TODO: hand-author scenarios here` block — better to surface the gap than to invent steps.
