---
name: test-design-advisor
description: Advise on test design — assess testability, recommend the right test-pyramid layer and test-double strategy, and propose a behavior-preserving refactor sequence to make hard-to-test code testable. Use when the user says "how should I test this", "is this testable", "design tests for this", "what's the right test for X", or before writing tests for an untested module.
role: worker
user-invocable: true
---

# Test Design Advisor

## Overview

An **advisory** skill: it recommends how to test code and how to make untestable code testable. It does not write tests or refactor code — it produces a design the human (or `/build`) then implements. Use it before writing a test suite for an untested or hard-to-test module, or when a test is hard to write and you suspect the design is the cause.

Grounded in these knowledge references: `knowledge/test-smells.md`, `knowledge/test-doubles.md`, `knowledge/test-pyramid.md` (layers + shapes), `knowledge/test-layer-gates.md` for behavior pre-gates, `knowledge/microservice-testing.md`, `knowledge/testability-patterns.md` for production-code seams, and `knowledge/test-strategy.md` for fixture and SUT-interaction strategy. On match it overlays `knowledge/testing-techniques/` (specialized techniques), resolves tools from `knowledge/test-stack-profiles/<stack>.md`, and may adapt a worked template from `knowledge/test-matrix-examples/`.

## Constraints

- Advisory only. Do not edit production code or write test files — output a recommendation.
- A hard-to-test design is a production-code problem. Recommend the seam (constructor injection, interface extraction), never a test workaround (reflection, `InternalsVisibleTo`, mocking concrete classes).
- Prefer the lowest test-pyramid layer that can verify the behavior; prefer state verification and the simplest double.
- Refactor sequences must be behavior-preserving and start with characterization tests when the code is currently untested.
- Be concise: tables and ordered steps, not prose. No restating the source material — cite the knowledge file.
- **Altitude boundary.** When a gate mandates application-level E2E/browser architecture, flag the seam (`→ cd-test-architecture`) and defer the harness/pipeline design to the `cd-test-architecture` skill — do not design the E2E harness here.
- **Terminology.** Layer labels (unit / integration / component / contract / E2E) map to `cd-test-architecture.md`'s six test types; keep them consistent (see its *Terminology Reconciliation* section).

## Parse Arguments

Arguments: target file(s), module, or a description of the code to test. If no target is given, ask for one. Detect language **and framework/stack** (from manifests — `package.json`, `build.gradle`/`pom.xml`, `*.csproj`, `go.mod`, `requirements.txt`/`pyproject.toml`, and frontend deps like react/vue/htmx) so tool resolution can pick the right `test-stack-profiles/<stack>.md`. Detect whether the target crosses independently-deployable service boundaries (load `microservice-testing.md` only if so).

## Steps

### 1. Assess testability

Read the target. For each unit, determine whether it can be constructed and driven through its public API with controlled inputs. Use the decision flow in `knowledge/testability-patterns.md`. Record blockers: static factories/singletons, new-ed-up dependencies, hidden global/clock/RNG access, concrete-class coupling, private logic with no public path.

### 1b. Behavior pre-gates (escalate the layer by failure mode)

Before pyramid placement, run the gates in `knowledge/test-layer-gates.md`. They **escalate upward only** — never lower the Step 2 pick; silent when none fire:

- **Gate A** user-facing dynamic → E2E alongside lower layers (state cost + amortization)
- **Gate B** bug fix → regression at the discovery layer (no escalation above it)
- **Gate C** HTMX/Alpine/Turbo swap → browser test REQUIRED for the seam
- **Gate D** visual artifact → approval/screenshot (with a reference) or manual

If dynamic-ness is ambiguous, state your assumption and ask **once** (batch ambiguities; offer "treat all as dynamic") — never escalate silently. When a gate mandates app-level E2E, flag it `→ cd-test-architecture` and defer the harness design there.

### 2. Place each behavior on the pyramid

Using `knowledge/test-pyramid.md`, assign each behavior to the lowest layer that can meaningfully verify it (unit / integration / component / contract / E2E). Flag anything currently mis-layered. For service boundaries, apply contract testing per `knowledge/microservice-testing.md` instead of E2E.

**Redundancy check (business-critical only).** After placement, for any behavior determined business-critical (labelled, or confirm by asking), if it is covered at only one layer, flag it and name a second layer with a different failure mode (catches/misses table in `test-layer-gates.md`) plus a concrete recommendation.

**Gate-column output schema.** In the *Pyramid placement* table the `Gate` column uses: `—` (no gate), `↑<layer>` (escalated), `→ cd-test-architecture` (E2E architecture deferred). When multiple gates fire, union the layers (no duplicate) and list each gate's cost once, with reconciliation guidance if the amortization advice differs.

**Tool resolution (by detected stack).** After the layer is fixed, name the concrete tool. If the detected stack has a profile in `knowledge/test-stack-profiles/<stack>.md`, read it and fill the `Tool` column from its layer→tool map (e.g. Spring integration → MockMvc; SSR frontend → JSDOM+MSW, **not** a browser unit runner). If no profile matches, proceed with stack-agnostic guidance and **name the missing profile** in the report — never block on it.

**Few-shot templates.** When building a multi-behavior matrix for a common stack, you *may* load a worked example from `knowledge/test-matrix-examples/` as a template and adapt its rows — never copy it verbatim.

### 2b. Specialized technique overlay (on trigger match)

Some behaviors break in a way no pyramid layer addresses. Consult `knowledge/testing-techniques/` and add a technique **only when its trigger matches** — silent otherwise. Each overlay note states the technique and its maintenance cost; it complements (does not replace) the layer pick.

| Trigger | Overlay | File |
|---------|---------|------|
| Invariant/law holds for all inputs | property-based | `property-based.md` |
| Parses untrusted/unstructured input | fuzz | `fuzz.md` |
| Large text/structured artifact vs a reference | approval | `approval.md` |
| Visual/CSS/layout fidelity matters | screenshot | `screenshot.md` |
| Payload governed by a declared schema (OpenAPI/JSON Schema/Avro) | schema-validation | `schema-validation.md` |
| Resilience claim under dependency failure | chaos | `chaos.md` |

**Exclusion.** Do **not** add a contract-testing technique here. Consumer↔provider agreement across an owned service boundary routes to `knowledge/microservice-testing.md` (CDC) — never double-route.

### 3. Choose doubles

For each collaborator at each test, recommend the simplest double using the decision flow in `knowledge/test-doubles.md` (dummy/stub/spy/mock/fake) and whether to verify by state or behavior. Default to state verification + stub/fake; reserve mock/spy for true side-effect boundaries.

### 3b. Recommend fixture and interaction strategy

Using `knowledge/test-strategy.md`, recommend per test group: fixture design + lifecycle (default Minimal + Fresh; escalate to Immutable Shared → Shared only under measured speed pressure), how the test is driven (scripted default; data-driven when variation is purely data), and SUT interaction (front-door by default; Layer Test for layered code; Back Door Manipulation only when the front door obscures intent). Flag any reliance on a mutable Shared Fixture as an Interacting-Tests risk.

### 4. Propose a behavior-preserving refactor sequence (only if blockers exist)

If Step 1 found blockers, produce an ordered sequence that makes the code testable without changing behavior:

1. Add characterization tests around current behavior (if untested) — pin existing behavior first.
2. Introduce the seam (the specific pattern from `testability-patterns.md`).
3. Write the now-possible tests at the layer from Step 2.
4. Refactor under green.

Each step names the pattern and the exact production change required.

### 5. Report

Write the recommendation (see Output). Keep it actionable — every recommendation maps to a concrete next edit.

## Output

A concise advisory report (to chat for a single unit, or to `reports/test-design-<target>.md` for a module):

```markdown
## Test Design — <target>

### Testability
| Unit | Testable as-is? | Blocker | Seam (testability-patterns.md) |

### Pyramid placement
| Behavior | Layer | Gate | Tool | Why this layer |

(`Tool` from the stack profile, or `—` / "no profile: <stack>" when none matches.)

### Technique overlay (only if a trigger fired)
| Behavior | Technique | Cost note |

### Double strategy
| Test | Collaborator | Double | Verify by |

### Refactor sequence (if blockers)
1. <characterization tests> → 2. <seam> → 3. <tests> → 4. <refactor>

### Next edit
<the single concrete first action>
```

## Integration

- Pairs with the `test-smell-review` agent (which *detects* smells) and the `test-design-reviewer` skill (which *scores* an existing suite). This skill *designs* tests forward.
- For application-level test architecture (CD pipeline alignment, deterministic config-free CI gate, per-component UI/service/batch patterns), defer to the `cd-test-architecture` skill and its knowledge files (`cd-test-architecture.md`, `component-test-patterns.md`). This skill stays at unit/module altitude.
- Hand the refactor sequence to `/plan` or `/build` for TDD implementation. This skill stops at the design.
