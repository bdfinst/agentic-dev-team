---
name: cd-test-architecture
description: Evaluate an existing application's tests and recommend a CD-pipeline-aligned test architecture — fast, deterministic tests with minimal tooling that fully validate behavior (including cross-service interaction) and run in CI without configuring the rest of the system. Use when the user says "evaluate how this app is tested", "design a test architecture", "align our tests for CD", "make our CI tests deterministic", "our tests need the whole system configured", "our tests live in another repo / Postman / manual scripts", or asks for UI/service/batch test patterns.
role: worker
user-invocable: true
---

# CD Test Architecture

## Overview

An **advisory, application-level** skill: it assesses how an existing application is tested, classifies that against a CD-aligned test taxonomy, finds the tests that can't run in a clean CI gate, and recommends a target architecture plus a migration path. It does not write tests or refactor code.

Where `test-design-advisor` works at the unit/module level and `test-smell-review` finds smells in test files, this skill works at the **whole-application** level: test types, pipeline stages, and per-component patterns.

Grounded in two knowledge references — read both before assessing:

- `knowledge/cd-test-architecture.md` — the six test types, the determinism→pre-merge-gate rule, the adapter rule, double validation, pipeline stages, and MinimumCD-vs-Fowler terminology.
- `knowledge/component-test-patterns.md` — per-component patterns (UI / Services / Batch) with isolation strategy and pipeline placement.

## Constraints

- Advisory only. Assess and recommend; do not edit production or test code. Hand the migration steps to `/plan` or `/build`.
- Use MinimumCD vocabulary (unit / component / contract / integration / E2E / static analysis) consistently; when the codebase uses other names, map them explicitly.
- The pre-merge gate may contain **only deterministic** tests (static, unit, component, contract). Any test that needs a database, broker, downstream service, or environment secrets configured to run is, by definition, not a pre-merge test — flag it.
- Recommend isolation via in-memory doubles + owned adapters, validated by the double-validation loop. Do **not** recommend standing up the whole system (docker-compose of dependencies) for the gate — that is the configured-dependency problem this architecture removes.
- **Do not assume provider cooperation.** For dependencies the team doesn't control, the defense against contract breakage is consumer-owned, scheduled verification against the provider's test environment (out-of-band) plus consumer resilience — not provider-side CDC verification. Recommend accordingly.
- Minimal tooling: prefer in-memory doubles, one real browser for UI, testcontainers only for off-gate adapter integration. Don't recommend a sprawl of frameworks.
- Be concise: tables and ordered steps, not prose. Cite the knowledge file instead of restating it.

## Parse Arguments

Arguments: a target application/repo path or description. Optional `--component <name>` to scope to one component, `--ci <path>` to point at the existing pipeline config, and **`--external-tests <path-or-repo-or-description>`** to point at tests that live outside this repo (another repo's suite, a third-party runner, Postman/Insomnia collections, manual test scripts, recorded UI flows, spreadsheets of test cases). If little or no in-repo testing is found and no external location is given, **ask** where the application is actually tested before concluding it is untested. If no target is given, ask for one.

## Steps

### 1. Inventory the application's components

Map the deployable/testable surfaces and assign each its pattern from `component-test-patterns.md` (User Interface; API Provider / API Consumer / Event Consumer / Event Producer / Stateful Service / CLI-Library; Scheduled Job). A real system is usually several — list each surface.

### 2. Inventory the existing tests and classify them

Find the test suites **in the repo** and classify each against the six types in `cd-test-architecture.md`. For each, record: type, what it actually exercises, whether it is deterministic, and **what it requires to run** (DB URL, broker, downstream service, secrets, sleep, real clock).

If in-repo tests are sparse or absent, the application is not necessarily untested — it may be tested out-of-repo (see Step 2b). Do not conclude "no tests" without checking.

### 2b. Locate and harvest out-of-repo tests

When `--external-tests` is given (or in-repo tests are sparse and the user points you to external coverage), treat the external location as the **current specification of intended behavior** and harvest it:

- **Other-repo automated suites** — read the suites; classify them by type just like in-repo tests; note that they live outside the component's repo and pipeline.
- **Postman / Insomnia / `.http` collections** — each request + its assertions describes an API contract and a scenario. Extract: endpoint, request shape, expected response, and which success/failure scenario it covers.
- **Manual test scripts / spreadsheets / recorded UI flows** — extract each step as a behavior the team cares about (a candidate component/E2E scenario), and note it is currently human-executed and non-repeatable.

Produce a behavior inventory from these sources, mapped to the component patterns from Step 1. This becomes the **basis for improvement** — the behaviors to re-express as deterministic, in-repo, gated tests.

### 3. Diagnose CD-fitness gaps

Flag, with evidence:

- **Out-of-repo / third-party-runner testing** — the component's tests live in another repo, a separate QA runner, Postman collections, or manual scripts rather than alongside the code. **This is an anti-pattern**, even when that external coverage is extensive: the tests cannot gate the component's own merges, are not versioned with the code they verify, are usually non-deterministic and environment-coupled, and silently drift from the code. The goal state is deterministic tests co-located with the code and run in its pipeline. Flag this explicitly and treat the external suite as the *source material* (Step 2b), not the destination.
- **Manual / non-repeatable testing** — behavior verified only by humans following scripts. Non-repeatable, unsuitable for any gate; each such script is a behavior to automate.
- **Mis-typed gate tests** — "unit/component" tests that require a real dependency or are non-deterministic (real clock/RNG/network/sleep). These cannot be a pre-merge gate.
- **Configured-dependency tests** — tests that need the rest of the system stood up to run.
- **Coverage gaps** — behavior (success + failure modes per the component pattern) not covered at any deterministic layer.
- **Drift risk** — doubles with no validation loop. In particular, assume **no provider cooperation**: a contract that nobody runs against the real provider on a schedule is undefended. Flag the absence of *consumer-owned, scheduled provider-contract verification in a test environment* — relying on provider-side CDC verification is not sufficient for providers you don't control.
- **No resilience to a broken contract** — the consumer assumes the provider holds; no tests that it survives a provider break (timeout, retry/backoff, circuit breaker, drifted/malformed response). Assume the provider *will* break without versioning.
- **Inverted shape** — reliance on integration/E2E where component/contract tests would gate deterministically.

### 4. Recommend the target architecture

Per component, using its pattern: which test types cover which layers, **what to double to run pre-merge without configuration**, the success scenarios and failure modes to cover, the double-validation loop, and the pipeline stage for each (pre-merge gate vs Stage 1/2 vs out-of-band vs post-deploy). Show the resulting pre-merge gate is deterministic and config-free.

### 5. Produce a migration path

Order the moves from current → target, lowest-risk first. When tests are out-of-repo (Step 2b), the path **starts by bringing the behavior in**: for each harvested behavior, re-express it as the lowest-layer deterministic in-repo test that covers it (Postman request → component/contract test; manual UI script → UI component test with the backend network-stubbed; other-repo E2E → in-repo component test + a thin post-deploy smoke), then retire the external case once its behavior is covered in the gate. Typical full sequence: harvest external coverage into an in-repo behavior inventory → introduce owned adapters → add in-memory doubles + component tests reproducing the harvested behaviors → add contract tests → add consumer resilience tests (survive a provider break) → add scheduled provider-contract verification against a test environment → move real-dependency tests off the gate to adapter-integration/out-of-band → add post-deploy checks → decommission the out-of-repo/manual suites as their behaviors land in the gate. Each step is behavior-preserving and independently shippable.

### 6. Report

Write the assessment (see Output). Keep every recommendation tied to a concrete next action.

## Output

Write to `reports/cd-test-architecture-<app>.md` (or chat for a single component):

```markdown
## CD Test Architecture — <app>

### Components & patterns
| Component | Pattern | Surfaces |

### Current tests (in-repo)
| Suite | MinimumCD type | Deterministic? | Requires to run | Pre-merge-safe? |

### Out-of-repo / external test sources (if any)
| Source (repo / Postman / manual / …) | Location | Behaviors it covers | Why it's an anti-pattern here |

### CD-fitness gaps
| Gap | Type | Evidence (file) | Impact |

### Target architecture (per component)
| Component | Layer | Test type | Double (to run config-free) | Pipeline stage |

### Pre-merge gate (deterministic, config-free)
<the set of suites that will gate merges, and why each is deterministic>

### Migration path
1. … → 2. … (lowest-risk first, each independently shippable)

### Next steps
- Refactor/seams → /plan or /build
- Per-file smells → /test-design
```

## Integration

- Pairs with `test-design-advisor` (unit/module design) and the `test-smell-review` / `test-review` agents (per-file findings). This skill sets the application-level target those operate within.
- Hand the migration path to `/plan` or `/build` for TDD implementation. This skill stops at the architecture and plan.
