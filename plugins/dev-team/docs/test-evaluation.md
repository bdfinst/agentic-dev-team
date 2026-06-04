# Test Evaluation and Architecture

This document explains how to evaluate how an existing application is tested and design a path toward a fast, deterministic, config-free CI gate that fully validates behavior — including cross-service interaction — without standing up the rest of the system.

## Purpose

The test evaluation workflow answers two questions: "how well is this application tested today?" and "what would a CD-aligned test architecture look like?" The result is an assessed gap list and a concrete migration path, not generated test code. Implementation of the migration goes to `/plan` or `/build`.

---

## Tools and Their Altitudes

Three tools operate at different scopes. Use the one that matches what you need.

| What you want | Tool | Altitude |
|---|---|---|
| Review test files in a changeset for smells and quality | `/test-design` | Per-file / changeset |
| Advise on how to test a specific module or hard-to-test unit | `test-design-advisor` skill | Unit / module |
| Assess the whole application's test strategy and pipeline alignment | `cd-test-architecture` skill | Whole application |

**`/test-design`** is the orchestrator command for the changeset-level workflow. It dispatches `test-review` (tactical quality: missing assertions, non-determinism mechanics, mock hygiene) and `test-smell-review` (design-level smells: xUnit smell taxonomy, double selection, pyramid placement) in parallel, then optionally runs `test-design-advisor` for production code that has no tests or hard-to-test units.

**`test-design-advisor`** works at the module level: assess testability blockers, place each behavior on the pyramid, choose the right test double, and produce a behavior-preserving refactor sequence to introduce seams. It does not write tests.

**`cd-test-architecture`** works at the application level: inventory components and test suites, classify against the six MinimumCD test types, identify CD-fitness gaps, recommend a per-component target architecture, and produce a migration path. It does not write tests or edit code.

---

## The Evaluation Workflow

The `cd-test-architecture` skill follows these steps. Run it with `/cd-test-architecture <path>`.

### Step 1: Inventory the application's components

Map each deployable or testable surface and assign it a pattern from `knowledge/component-test-patterns.md`:

- **UI** — User Interface
- **Services** — API Provider, API Consumer, Event Consumer, Event Producer, Stateful Service, CLI/Library
- **Batch** — Scheduled Job

A real system is usually several of these. Each surface is assessed separately.

### Step 2: Inventory and classify existing tests

Find every test suite in the repo. For each, record: MinimumCD type, what it actually exercises, whether it is deterministic, and what it requires to run (DB URL, broker, downstream service, secrets, sleep, real clock).

If in-repo tests are sparse, the application is not necessarily untested — see Step 2b before concluding.

### Step 2b: Locate and harvest out-of-repo tests

When `--external-tests <path-or-repo-or-description>` is given, treat the external location as the current specification of intended behavior:

- **Other-repo suites** — read and classify just like in-repo tests; note they can't gate this component's merges.
- **Postman/Insomnia/`.http` collections** — extract each request + assertion as an API contract and scenario.
- **Manual scripts or spreadsheets** — extract each step as a behavior to automate.

This produces a behavior inventory that becomes the basis for improvement, not the destination.

### Step 3: Diagnose CD-fitness gaps

Flag, with evidence:

- Out-of-repo or third-party-runner testing (anti-pattern — see below)
- Manual / non-repeatable testing
- Tests mistyped as "unit" that require real dependencies
- Configured-dependency tests that can't run in a clean CI gate
- Coverage gaps (success + failure modes not covered at any deterministic layer)
- Doubles with no validation loop (drift risk)
- No consumer resilience tests (the component assumes the provider holds)
- Inverted pyramid shape (integration/E2E doing what component tests should)

### Step 4: Recommend the target architecture

Per component: which test types cover which layers, what to double to run pre-merge without configuration, which success scenarios and failure modes to cover, the double-validation loop, and the pipeline stage for each test type (pre-merge gate, Stage 1/2, out-of-band, or post-deploy).

### Step 5: Produce a migration path

Ordered lowest-risk first, each step independently shippable. The spine is **baseline before refactor**: get behavior under test at existing seams *without changing code*, then refactor under that green baseline. When tests are out-of-repo, the harvested behaviors feed that baseline. Typical full sequence:

1. **Characterization baseline (no refactoring)** — outside-in tests at the outermost reachable seam that lock in current behavior; reproduce any harvested out-of-repo/manual behaviors here. Get green.
2. Introduce owned adapters and seams **under the baseline** (DDD skills suggest where boundaries belong)
3. Add in-memory doubles + component tests reproducing the baselined behaviors
4. Add contract tests pinning request/response boundaries
5. Add consumer resilience tests (verify the component survives a provider break)
6. Add scheduled provider-contract verification against a test environment
7. Move real-dependency tests off the gate to adapter integration or out-of-band
8. Add post-deploy checks
9. Decommission out-of-repo/manual suites and the coarse characterization tests as their behaviors land in the deterministic gate

### Step 6: Report

Output goes to `reports/cd-test-architecture-<app>.md`. Tables, not prose: components and patterns, current tests and their CD-fitness, gaps, target architecture, pre-merge gate composition, migration path, next steps.

---

## When the Tests Aren't in the Repo

An application may have little or no in-repo testing and instead be covered by suites in another repo, a third-party runner, Postman or Insomnia collections, or manual scripts. This is an **anti-pattern** regardless of how thorough the external coverage is:

- The tests **cannot gate the component's own merges** — the build can go green while behavior is broken.
- The tests are **not versioned with the code** they verify; a code change and its test change can't move together.
- External suites are usually **non-deterministic and environment-coupled**, so they could never serve as a pre-merge gate anyway.
- **Manual scripts are not repeatable** — they're a checklist, not a regression net.

This does not mean the external coverage is worthless. It is the **current specification of intended behavior** — the best available basis for improvement.

To include it in the assessment, point the skill at it:

```
/cd-test-architecture <path> --external-tests <postman-collection.json>
/cd-test-architecture <path> --external-tests <path-to-other-repo>
/cd-test-architecture <path> --external-tests "manual regression scripts in Confluence, linked here: ..."
```

The skill harvests those sources as a behavior inventory (Step 2b) and builds the migration path around re-expressing each behavior as a deterministic, in-repo, gated test:

| External source | Re-expressed as |
|---|---|
| Postman request + assertion | Component or contract test |
| Manual UI script | UI component test (real browser, network stubbed) |
| Other-repo E2E covering this component | In-repo component test + thin post-deploy smoke |

Each external case is decommissioned once its behavior lands in the gate.

If in-repo tests are sparse but no `--external-tests` location is given, the skill will **ask** where the application is actually tested before drawing any conclusions.

---

## Key Principles

### Pre-merge gate: deterministic tests only

The gate that blocks a merge may contain **only** static analysis, unit, component, and contract tests. These are deterministic and need nothing configured. Integration and end-to-end tests are non-deterministic by nature and never gate a merge. A test that needs a database URL, broker, downstream service, or environment secrets to run is mis-typed — re-classify or convert it.

### Run CI without configuring dependencies

The component test is the workhorse of a CD gate. The pattern is consistent across every component type:

1. Assemble the **real component** — actual handlers, domain logic, orchestration — in-process.
2. Replace only what the team doesn't control with **in-memory doubles**: in-memory repository for the database, in-memory bus for the broker, stubbed adapter for downstream services, injected fixed clock.
3. Drive it through its **public interface** — HTTP handlers, message handler, job entrypoint, UI via a real browser with the network stubbed.
4. Assert **observable outcomes** — status, persisted state, emitted event, rendered output — never internal call sequences.

The result: fast (no I/O), deterministic (no real systems, controlled clock), zero configuration of the surrounding system — while still validating real behavior end-to-end within the component boundary.

### The adapter rule

Wrap every third-party client (SDK, HTTP client, broker client, DB driver) in a thin adapter the team owns. Double the adapter in component tests — never mock the third-party SDK directly. Adapter integration tests then exercise the real adapter against a real container to confirm the adapter's correctness.

### Do not depend on provider cooperation

Consumer-driven contract verification where the provider runs your contract in their pipeline only works with close collaboration and enforced tooling. Assume you do not have that. The defense you own:

1. **Contract tests** (pre-merge) pin the request you send and the response shape you depend on, against the adapter double.
2. **Scheduled provider-contract verification in a test environment** — you run your pinned contract against the provider's real non-prod endpoint on a schedule, out-of-band, owned by your team. This detects a provider break when it happens, not at your next unrelated deploy.
3. **Resilience component tests** (pre-merge) verify the consumer survives a broken contract: timeouts enforce, retries and circuit breakers behave, malformed responses are handled, the caller gets a documented response with no partial state.

Provider-side verification of your contract is a bonus if they offer it — not the mechanism to rely on.

### Baseline before refactor (legacy code)

Legacy code is code without tests (regardless of age). When a component is poorly tested, **do not lead with refactoring**:

1. **Find the testable seams** — places where behavior can be observed or substituted without editing the code (HTTP handler, CLI entrypoint, message handler, exported function, existing injection points).
2. **Write the best outside-in tests achievable now, without refactoring** — characterization tests at the outermost reachable seam that lock in current behavior. This is a behavior baseline, not yet a clean gate.
3. **Get the baseline green** — your safety net.
4. **Refactor to improve testability under green** — introduce adapters and seams, push checks down to deterministic component/unit tests. Never change behavior and structure in the same step.
5. **Let the domain guide the target** — the `domain-driven-design` and `domain-analysis` skills suggest where boundaries and seams should land.

The mechanics live in the [`legacy-code`](../skills/legacy-code/SKILL.md) skill; this workflow places it in the CD test architecture. An assessment of an under-tested component therefore returns two things: the outside-in baseline writable today, and the refactor sequence that improves testability afterward.

---

## Sample Invocations

```bash
# Full application assessment
/cd-test-architecture ./src

# Scope to one component
/cd-test-architecture ./src --component payment-service

# Include existing CI config in the assessment
/cd-test-architecture ./src --ci .github/workflows/ci.yml

# Application tested primarily via Postman collections
/cd-test-architecture ./src --external-tests ./test-collections/api-tests.postman_collection.json

# Application tested in another repo
/cd-test-architecture ./src --external-tests "../qa-repo/e2e/payment-service"

# Per-file / changeset review (current working tree or staged changes)
/test-design

# Per-file review scoped to a directory
/test-design --path src/payments

# Per-file review of changes since a branch
/test-design --since main

# Unit/module design advice (advisory — does not write tests)
/test-design-advisor src/payments/PaymentProcessor.ts
```

---

## Reference Files

| File | What it defines |
|---|---|
| [`knowledge/cd-test-architecture.md`](../knowledge/cd-test-architecture.md) | Six MinimumCD test types, the pre-merge gate rule, out-of-repo anti-pattern, component test pattern, adapter rule, double validation, determinism techniques |
| [`knowledge/component-test-patterns.md`](../knowledge/component-test-patterns.md) | Per-component patterns: UI, API Provider, API Consumer, Event Consumer, Event Producer, Stateful Service, CLI/Library, Scheduled Job |
| [`knowledge/test-smells.md`](../knowledge/test-smells.md) | xUnit smell taxonomy: code, behavior, and project smells |
| [`knowledge/test-doubles.md`](../knowledge/test-doubles.md) | Dummy / stub / spy / mock / fake selection and state-vs-behavior verification |
| [`knowledge/test-pyramid.md`](../knowledge/test-pyramid.md) | Pyramid layer responsibilities and shape anti-patterns |
| [`knowledge/microservice-testing.md`](../knowledge/microservice-testing.md) | Contract and CDC testing across independently-deployable services |
| [`skills/cd-test-architecture/SKILL.md`](../skills/cd-test-architecture/SKILL.md) | The application-level assessment skill |
| [`skills/test-design-advisor/SKILL.md`](../skills/test-design-advisor/SKILL.md) | The unit/module design advisor skill |
| [`skills/legacy-code/SKILL.md`](../skills/legacy-code/SKILL.md) | Characterization testing + dependency-breaking: the baseline-before-refactor procedure |
| [`skills/domain-driven-design/SKILL.md`](../skills/domain-driven-design/SKILL.md) | Suggests target boundaries/seams for the post-baseline refactor |
| [`commands/test-design.md`](../commands/test-design.md) | The `/test-design` orchestrator command |
| [`agents/test-smell-review.md`](../agents/test-smell-review.md) | The smell-detection review agent |
