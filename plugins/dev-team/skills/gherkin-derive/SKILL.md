---
name: gherkin-derive
description: >-
  Derive Gherkin scenarios directly from a codebase — standalone, with no
  prior legacy-modernization analysis. Discovers the public surface (OpenAPI,
  routes, existing tests, then exported signatures), recommends a BDD binding
  mode via the bdd-value-guide rubric, and writes `.feature` files plus
  (in bdd-runner mode) pending step-definition stubs. Use it on its own to
  capture intended behavior before changing tests, or as Phase 1b of
  `/test-upgrade`. Unlike `/gherkin-public` it needs no `/test-modernize`
  component map and creates no tracker Stories.
argument-hint: "<repo-path> [--mode none|xunit-with-annotations|bdd-runner] [--repo-slug <slug>]"
role: worker
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Gherkin Derive

Role: worker. A **standalone** Gherkin derivation skill. It derives scenarios for
a repo's public surface directly from code — it does **not** require
`memory/test-modernize/<slug>/phase-1.md` or any prior `/cd-test-architecture`
analysis, and it does **not** create tracker Stories (that is `/test-upgrade`
Phase 2's job). `/gherkin-public` is unchanged and remains the `/test-modernize`
Phase-2 worker.

Usable two ways: on its own to capture intended behavior before any test change,
or as the Phase-1b sub-step of `/test-upgrade`.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--mode <none|xunit-with-annotations|bdd-runner>` — the binding mode. When
  omitted, present the BDD value rubric (Step 1) and let the operator choose.
- `--repo-slug <slug>` — namespace for the surface inventory under
  `memory/test-upgrade/<slug>/`.

## Step 1 — Choose the binding mode (BDD value rubric)

If `--mode` was **not** supplied, present the 5-question rubric from
`knowledge/references/bdd-value-guide.md` and recommend a mode from the score:

- `≥ 3 yes` → **`bdd-runner`**
- `1–2 yes` → **`xunit-with-annotations`**
- `0 yes` → **`none`**

Show the recommendation and let the operator override. The three modes:

- **`none`** — emit no Gherkin. Exit immediately with a one-line recommendation
  to use plain xUnit (e.g. *"0/5 BDD signals — use plain xUnit; no `.feature`
  files written."*). **Write no files.**
- **`xunit-with-annotations`** — derive scenarios and write `.feature` files, but
  do **NOT** wire a BDD runner or install any framework. The files are
  documentation that `/build` cites in test method names and leading comments.
- **`bdd-runner`** — derive scenarios, write `.feature` files, wire the
  language-appropriate BDD framework (Step 4), and generate pending step
  definition stubs.

## Step 2 — Discover the public surface

No pre-computed component map is required. Discover surfaces in this **priority
order**, most authoritative first:

1. **OpenAPI / Swagger spec** (`openapi.yaml`, `openapi.json`, `swagger.json`) —
   the most authoritative description of the public surface. Each path+method is
   a surface.
2. **Route definitions** — Express/Fastify handlers, Spring `@Controller` /
   `@RestController`, ASP.NET `[ApiController]`, Go `http.HandleFunc` / Chi / Gin
   routes. Each registered route is a surface.
3. **Existing test names** — `describe` / `it` / `[Fact]` / `@Test` blocks. These
   yield **characterization** scenarios (current behavior, not intended
   behavior). Use them only when OpenAPI and routes do not already cover the
   surface.
4. **Public function signatures + docstrings** — exported functions/classes with
   doc comments. The lowest-priority fallback for libraries with no HTTP surface.

Stop climbing the list once a surface is described by a higher-priority source —
do not duplicate a route's scenarios from its tests.

## Step 3 — Author scenarios

Use the same templates as `/gherkin-public`: **API Provider**, **UI**,
**Batch / Scheduled Job**, **CLI / Library**, **API / Event Consumer**. Every
scenario covers at least one success and one failure path, and every step is
observable at the boundary — no internal calls.

**Label the provenance** in each `.feature` file header:

- Scenarios derived from OpenAPI or docstrings are **specification** scenarios
  (intended behavior).
- Scenarios derived from existing tests or code are **characterization**
  scenarios — the header MUST state `# Characterization: current behavior, not
  intended behavior` so a reader never mistakes a captured bug for a spec.

```gherkin
# Source: <openapi path | route | test file | signature>
# Provenance: specification | characterization
# Characterization: current behavior, not intended behavior   (characterization only)
Feature: <surface>
  Scenario: <success path>
    ...
  Scenario: <failure path>
    ...
```

## Step 4 — Wire the BDD framework (bdd-runner mode only)

Skip this step entirely in `none` and `xunit-with-annotations` modes.

Read `knowledge/test-stack-profiles/bdd-frameworks.md` for the per-language install steps
and directory layout, then generate **pending** step-definition stubs so the
suite **compiles and fails intentionally** (red before green) — never empty stubs
that pass silently.

| Language | Framework | Pending stub |
|---|---|---|
| JS/TS | Cucumber.js | `return this.pending();` |
| Java (Maven) | Cucumber-JVM + `cucumber-junit-platform-engine` | `throw new io.cucumber.java.PendingException();` |
| Java (Gradle) | Same via Gradle config | `throw new io.cucumber.java.PendingException();` |
| C# | Reqnroll (xUnit / NUnit / MSTest) | injected `ScenarioContext.StepIsPending()` |
| Go | Godog | `return godog.ErrPending` |

## Step 5 — Output

- `features/<surface>.feature` files (all non-`none` modes).
- `step_definitions/<surface>_steps.<ext>` pending stubs (`bdd-runner` only).
- A surface inventory at `memory/test-upgrade/<slug>/gherkin.md` listing each
  discovered surface, its discovery source, provenance, mode, and the files
  written. `/test-upgrade` reads this to bind component tests in Phase 3.

## Step 6 — Report

Print the mode, the count of surfaces by discovery source (OpenAPI / route /
test / signature), the specification-vs-characterization split, and the paths
written. In `none` mode, print only the one-line recommendation.

## Key differences from `/gherkin-public`

- Does **not** require `memory/test-modernize/<slug>/phase-1.md` — derives the
  surface itself.
- Does **not** create tracker Stories — `/test-upgrade` Phase 2 owns that.
- Usable standalone or as `/test-upgrade` Phase 1b.
- `/gherkin-public` is unchanged.

## Notes

- Characterization scenarios capture *what the code does now*. Flag any that look
  like latent bugs rather than silently encoding them as the spec.
- Where a UI flow cannot be inferred from code alone, emit a stub `.feature` with
  the header and a `# TODO: hand-author scenarios here` block — surface the gap
  rather than invent steps.
