---
name: cd-test-architecture
description: Evaluate an existing application's tests and recommend a CD-pipeline-aligned test architecture — fast, deterministic tests with minimal tooling that fully validate behavior (including cross-service interaction) and run in CI without configuring the rest of the system. Use when the user says "evaluate how this app is tested", "design a test architecture", "align our tests for CD", "make our CI tests deterministic", "our tests need the whole system configured", "our tests live in another repo / Postman / manual scripts", or asks for UI/service/batch test patterns.
role: worker
user-invocable: true
argument-hint: "[--component <name>] [--ci <path>] [--external-tests <path>] [--stack <id>] [--pdf]"
---

# CD Test Architecture

Role: worker. This command assesses and reports — it does not write tests or
refactor code; it hands the migration steps to `/plan` or `/build`; Step 4b's
build-vs-document ask is this skill's one interactive branch point, and even
there it proposes a Story rather than invoking `/build` itself.

## Overview

An **advisory, application-level** skill: it assesses how an existing application is tested, classifies that against a CD-aligned test taxonomy, finds the tests that can't run in a clean CI gate, and recommends a target architecture plus a migration path. It does not write tests or refactor code.

Where `test-design-advisor` works at the unit/module level and `test-smell-review` finds smells in test files, this skill works at the **whole-application** level: test types, pipeline stages, and per-component patterns.

Grounded in these knowledge references — read the first two before assessing:

- `knowledge/cd-test-architecture.md` — the six test types, the determinism→pre-merge-gate rule, the adapter rule, double validation, pipeline stages, and MinimumCD-vs-Fowler terminology.
- `knowledge/component-test-patterns.md` — per-component patterns (UI / Services / Batch) with isolation strategy and pipeline placement.
- `knowledge/database-test-patterns.md` — load when a component is database-backed: Database Sandbox isolation, Transaction Rollback / Table Truncation Teardown, and the rule that pushes most data-logic tests onto in-memory Fakes so they stay pre-merge-gate eligible.

## Constraints

- Advisory only. Assess and recommend; do not edit production or test code. Hand the migration steps to `/plan` or `/build` — including Step 4b's build-vs-document ask: it proposes a downstream Story, it never invokes `/build` or edits code directly.
- Use MinimumCD vocabulary (unit / component / contract / integration / E2E / static analysis) consistently; when the codebase uses other names, map them explicitly.
- The pre-merge gate may contain **only deterministic** tests (static, unit, component, contract). Any test that needs a database, broker, downstream service, or environment secrets configured to run is, by definition, not a pre-merge test — flag it.
- Recommend isolation via in-memory doubles + owned adapters, validated by the double-validation loop. Do **not** recommend standing up the whole system (docker-compose of dependencies) for the gate — that is the configured-dependency problem this architecture removes.
- **Do not assume provider cooperation.** For dependencies the team doesn't control, the defense against contract breakage is consumer-owned, scheduled verification against the provider's test environment (out-of-band) plus consumer resilience — not provider-side CDC verification. Recommend accordingly.
- **Baseline before refactor (don't lead with refactoring).** For under-tested or legacy components, first recommend the best outside-in test achievable *at existing seams without changing the code* — a characterization baseline — then the refactor that improves testability under that green baseline. Never change behavior and structure in the same step. Defer the procedure to the `legacy-code` skill and use the DDD skills (`domain-driven-design`, `domain-analysis`) to suggest the target structure for the refactor.
- Minimal tooling: prefer in-memory doubles, one real browser for UI, testcontainers only for off-gate adapter integration. Don't recommend a sprawl of frameworks.
- Be concise: tables and ordered steps, not prose. Cite the knowledge file instead of restating it.

## Parse Arguments

Arguments: a target application/repo path or description. Optional `--component <name>` to scope to one component, `--ci <path>` to point at the existing pipeline config, **`--external-tests <path-or-repo-or-description>`** to point at tests that live outside this repo (another repo's suite, a third-party runner, Postman/Insomnia collections, manual test scripts, recorded UI flows, spreadsheets of test cases), and `--stack <id>` to override stack detection (default: detect from manifests; resolved profile key like `dotnet`, `node`, `spring-boot`, `go`, `django`, `react`, `vue`, `ssr-htmx`). If little or no in-repo testing is found and no external location is given, **ask** where the application is actually tested before concluding it is untested. If no target is given, ask for one.

## Steps

### 0. Detect stack

Resolve the project's stack so the assessment can resolve concrete tools from `knowledge/test-stack-profiles/<stack>.md`. Mirrors `skills/test-design-advisor/SKILL.md:31, 62`: when `--stack <id>` is provided, **it takes precedence** and detection is skipped. Otherwise, read manifests at the target — `package.json` (refined to react/vue via dependency, or to ssr-htmx when an htmx dep is present alongside `templates/*.html`), `*.csproj` / `*.sln`, `pom.xml` / `build.gradle*`, `go.mod`, `pyproject.toml` / `requirements.txt` — and resolve the matching profile key. Load `knowledge/test-stack-profiles/<stack>.md` (and any references it points at) so the *Target architecture* table can name concrete tools per layer. When no profile matches, proceed with stack-agnostic guidance and **name the missing profile in the report** — never block on it.

### 1. Inventory the application's components

Map the deployable/testable surfaces and assign each its pattern from `component-test-patterns.md` (User Interface; API Provider / API Consumer / Event Consumer / Event Producer / Stateful Service / CLI-Library; Scheduled Job). A real system is usually several — list each surface.

**Graph-assisted inventory.** If the target repo has `.codegraph/` (CodeGraph MCP server, `mcp__codegraph__codegraph_explore` — fast callers/callees/impact lookups) and/or a Repowise MCP server (`get_context`/`search_codebase` — verified context and semantic search), prefer them over raw `Grep` for locating components, their deployable surfaces, and existing test suites. Never assume either is present — fall back to `Read`/`Grep`/`Glob` when absent; the tools are simply unavailable (no error) on repos without an index.

### 2. Inventory the existing tests and classify them

Find the test suites **in the repo** and classify each against the six types in `cd-test-architecture.md`. For each, record: type, what it actually exercises, whether it is deterministic, and **what it requires to run** (DB URL, broker, downstream service, secrets, sleep, real clock).

If in-repo tests are sparse or absent, the application is not necessarily untested — it may be tested out-of-repo (see Step 2b — locate and harvest out-of-repo tests). Do not conclude "no tests" without checking.

### 2b. Locate and harvest out-of-repo tests

When `--external-tests` is given (or in-repo tests are sparse and the user points you to external coverage), treat the external location as the **current specification of intended behavior** and harvest it:

- **Other-repo automated suites** — read the suites; classify them by type just like in-repo tests; note that they live outside the component's repo and pipeline.
- **Postman / Insomnia / `.http` collections** — each request + its assertions describes an API contract and a scenario. Extract: endpoint, request shape, expected response, and which success/failure scenario it covers.
- **Manual test scripts / spreadsheets / recorded UI flows** — extract each step as a behavior the team cares about (a candidate component/E2E scenario), and note it is currently human-executed and non-repeatable.

Produce a behavior inventory from these sources, mapped to the component patterns from Step 1 (inventory the application's components). This becomes the **basis for improvement** — the behaviors to re-express as deterministic, in-repo, gated tests.

### 3. Diagnose CD-fitness gaps

Flag, with evidence:

- **Out-of-repo / third-party-runner testing** — the component's tests live in another repo, a separate QA runner, Postman collections, or manual scripts rather than alongside the code. **This is an anti-pattern**, even when that external coverage is extensive: the tests cannot gate the component's own merges, are not versioned with the code they verify, are usually non-deterministic and environment-coupled, and silently drift from the code. The goal state is deterministic tests co-located with the code and run in its pipeline. Flag this explicitly and treat the external suite as the *source material* (Step 2b — locate and harvest out-of-repo tests), not the destination.
- **Manual / non-repeatable testing** — behavior verified only by humans following scripts. Non-repeatable, unsuitable for any gate; each such script is a behavior to automate.
- **Mis-typed gate tests** — "unit/component" tests that require a real dependency or are non-deterministic (real clock/RNG/network/sleep). These cannot be a pre-merge gate.
- **Configured-dependency tests** — tests that need the rest of the system stood up to run.
- **Coverage gaps** — behavior (success + failure modes per the component pattern) not covered at any deterministic layer.
- **Drift risk** — doubles with no validation loop. In particular, assume **no provider cooperation**: a contract that nobody runs against the real provider on a schedule is undefended. Flag the absence of *consumer-owned, scheduled provider-contract verification in a test environment* — relying on provider-side CDC verification is not sufficient for providers you don't control.
- **No resilience to a broken contract** — the consumer assumes the provider holds; no tests that it survives a provider break (timeout, retry/backoff, circuit breaker, drifted/malformed response). Assume the provider *will* break without versioning.
- **Inverted shape** — reliance on integration/E2E where component/contract tests would gate deterministically.

### 3b. Find testable seams and the achievable outside-in baseline

For each under-tested or untested component, identify the **testable seams** — places where behavior can be observed or substituted without editing the code (HTTP handler, CLI entrypoint, message handler, exported function, existing injection points; object seams via interfaces/polymorphism, link seams via DI/module substitution). Then state the **best outside-in test achievable right now without refactoring** — a characterization test at the outermost reachable seam that locks in current behavior. This is the immediate, zero-risk baseline, distinct from the (later) clean CD gate. See `cd-test-architecture.md` → Outside-In First, and the `legacy-code` skill.

### 4. Recommend the target architecture

Per component, using its pattern: which test types cover which layers, **what to double to run pre-merge without configuration**, the success scenarios and failure modes to cover, the double-validation loop, and the pipeline stage for each (pre-merge gate vs Stage 1/2 vs out-of-band vs post-deploy). Show the resulting pre-merge gate is deterministic and config-free. For under-tested components, separate the recommendation into **(a) the outside-in characterization baseline writable today without refactoring** and **(b) the post-baseline refactor** toward this target (use the DDD skills to suggest where boundaries/seams should land).

**E2E justification gate.** Never recommend an E2E test "for completeness" or "to round out the pyramid." For each E2E recommendation, document that **all four** conditions hold: (1) a **contract test** cannot pin the boundary that catches this behavior, (2) a **component test** with doubles cannot exercise it via the component's public interface, (3) a **resilience test** (timeout / retry / circuit-breaker / malformed response) cannot cover the failure mode, AND (4) the behavior is a critical user journey across multiple real components that cannot be decomposed. Record one sentence per behavior explaining why E2E was *not* chosen when (1)–(3) cover it. When E2E is genuinely required, name the user journey, the pipeline stage (post-deploy smoke; never pre-merge), and surface that E2E is non-deterministic per MinimumCD.

**The pyramid is a cost heuristic, not a target shape.** Do not recommend per-layer target counts or "current shape vs recommended shape" tables. Per-component / per-behavior placement is the valid output; if the suite shape is pathological, name the pathology (ice-cream cone, hourglass, cupcake) and the behaviors that suffer from it — do not propose a numeric redistribution.

### 4b. Build-vs-document decision (off-gate adapter test doubles)

When Step 4 identifies one or more components needing a testcontainers-based real-DB test, ask the operator once per run, batched across every such component regardless of adapter kind — this is the shared prompt later adapter-kind slices (#1434 downstream services, #1435 record-and-replay libraries) append to, not a new prompt each run — whether to:

1. **Build** — propose a downstream Story that the operator/orchestrator later drives `/build` against, or
2. **Document only** (default) — the recommendation lands in the report as today, with no further action.

Non-interactive runs (per `human-oversight-protocol`'s `--yes` / `DEV_TEAM_AUTO_APPROVE=1` / no-TTY convention) skip the prompt entirely — no prompt is surfaced, and the recommendation lands in the report only, document-only, exactly as today.

An ambiguous or absent answer to the batched build-vs-document question — for example "maybe", "I'm not sure", a bare "yes" or "no", or silence/empty input — is treated the same as document-only: never guessed, never blocked on.

Repos with no such gap see no behavior change: no prompt is asked, and the report is unchanged.

### 5. Produce a migration path

Order the moves from current → target, lowest-risk first. The spine is **baseline before refactor**: get behavior under test at existing seams *without changing code*, then refactor under that green baseline (never behavior + structure in one step). When tests are out-of-repo (Step 2b — locate and harvest out-of-repo tests), the harvested behaviors feed that baseline. Typical full sequence:

1. **Characterization baseline (no refactoring)** — at the outermost reachable seam, write outside-in tests that lock in current behavior; harvest any out-of-repo/manual behaviors into this inventory and reproduce them here. Get green.
2. **Introduce owned adapters and seams — under the baseline** (Adapter Rule; `testability-patterns.md`; DDD skills suggest where boundaries/seams belong). Refactor only with the baseline green.
3. Add in-memory doubles + deterministic **component tests** reproducing the baselined behaviors.
4. Add **contract tests** pinning request/response boundaries.
5. Add **consumer resilience tests** (survive a provider break).
6. Add **scheduled provider-contract verification** against a test environment.
7. Move real-dependency tests **off the gate** to adapter-integration / out-of-band.
8. Add **post-deploy checks**.
9. **Decommission** the out-of-repo/manual suites and the coarse characterization tests as their behaviors land in the deterministic gate.

Each step is behavior-preserving and independently shippable.

### 6. Report

Write the assessment (see Output). Keep every recommendation tied to a concrete next action.

## Output

Write to `.dev-team-reports/cd-test-architecture-<app>.md` (or chat for a single component).

When `--pdf` was passed and a report **file** was written, render it to a
sibling PDF per `knowledge/report-pdf-integration.md`:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/cd-test-architecture-<app>.md
```

In the single-component **chat-only** case no file was written, so `--pdf` is a
no-op: state `--pdf: no report file was written this run, nothing to render.`
and do nothing else. Additive; non-fatal if no engine is available.

For the header block and closing Provenance section, follow
`knowledge/report-template.md`; the sections below are this skill's own
body.

```markdown
# CD Test Architecture

**Date**: <ISO 8601>
**Target**: <app>
**Tool versions**: _Not applicable — no tool versions apply to this assessment._
**Scope**: <full app | single component>

## CD Test Architecture — <app>

### Components & patterns
| Component | Pattern | Surfaces |

### Current tests (in-repo)
| Suite | MinimumCD type | Deterministic? | Requires to run | Pre-merge-safe? |

### Out-of-repo / external test sources (if any)
| Source (repo / Postman / manual / …) | Location | Behaviors it covers | Why it's an anti-pattern here |

### CD-fitness gaps
| Gap | Type | Evidence (file) | Impact |

### Testable seams & achievable baseline (under-tested components)
| Component | Outermost seam | Best outside-in test writable today (no refactor) |

### Target architecture (per component)
| Component | Layer | Test type | Double (to run config-free) | Pipeline stage |

When Step 0 loaded a `knowledge/test-stack-profiles/<stack>.md` profile, **cite that profile** (and any reference it points at) in the *Test type* or *Double* column so the concrete tool choice is traceable to the stack-specific reference.

### Pre-merge gate (deterministic, config-free)
<the set of suites that will gate merges, and why each is deterministic>

### Migration path
1. … → 2. … (lowest-risk first, each independently shippable)

### Next steps
- Refactor/seams → /plan or /build
- Per-file smells → /test-design

## Provenance

- Repository: `<repo path>`
- Branch / SHA: `<branch>` / `<sha>`
- Run parameters: `<flags — e.g. single-component scope>`
- `dev-team` plugin version: `<plugin_version>`
```

## Integration

- Pairs with `test-design-advisor` (unit/module design) and the `test-smell-review` / `test-review` agents (per-file findings). This skill sets the application-level target those operate within.
- For under-tested/legacy components, the characterization-baseline-then-refactor procedure is the **`legacy-code`** skill (Feathers' algorithm: change points → test points/seams → break dependencies → characterization tests → refactor under green). Defer the mechanics to it.
- Use the **`domain-driven-design`** and **`domain-analysis`** skills to suggest the target structure for the post-baseline refactor — where bounded contexts, ports, and seams should land — so refactoring improves the domain model, not just testability.
- Hand the migration path to `/plan` or `/build` for TDD implementation. This skill stops at the architecture and plan, except that Step 4b may propose a downstream Story as part of that hand-off — it still never invokes `/build` itself.
