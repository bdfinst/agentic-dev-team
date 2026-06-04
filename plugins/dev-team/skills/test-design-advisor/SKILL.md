---
name: test-design-advisor
description: Advise on test design — assess testability, recommend the right test-pyramid layer and test-double strategy, and propose a behavior-preserving refactor sequence to make hard-to-test code testable. Use when the user says "how should I test this", "is this testable", "design tests for this", "what's the right test for X", or before writing tests for an untested module.
role: worker
user-invocable: true
---

# Test Design Advisor

## Overview

An **advisory** skill: it recommends how to test code and how to make untestable code testable. It does not write tests or refactor code — it produces a design the human (or `/build`) then implements. Use it before writing a test suite for an untested or hard-to-test module, or when a test is hard to write and you suspect the design is the cause.

Grounded in these knowledge references: `knowledge/test-smells.md`, `knowledge/test-doubles.md`, `knowledge/test-pyramid.md`, `knowledge/microservice-testing.md`, `knowledge/testability-patterns.md` for production-code seams, and `knowledge/test-strategy.md` for fixture and SUT-interaction strategy.

## Constraints

- Advisory only. Do not edit production code or write test files — output a recommendation.
- A hard-to-test design is a production-code problem. Recommend the seam (constructor injection, interface extraction), never a test workaround (reflection, `InternalsVisibleTo`, mocking concrete classes).
- Prefer the lowest test-pyramid layer that can verify the behavior; prefer state verification and the simplest double.
- Refactor sequences must be behavior-preserving and start with characterization tests when the code is currently untested.
- Be concise: tables and ordered steps, not prose. No restating the source material — cite the knowledge file.

## Parse Arguments

Arguments: target file(s), module, or a description of the code to test. If no target is given, ask for one. Detect language and whether the target crosses independently-deployable service boundaries (load `microservice-testing.md` only if so).

## Steps

### 1. Assess testability

Read the target. For each unit, determine whether it can be constructed and driven through its public API with controlled inputs. Use the decision flow in `knowledge/testability-patterns.md`. Record blockers: static factories/singletons, new-ed-up dependencies, hidden global/clock/RNG access, concrete-class coupling, private logic with no public path.

### 2. Place each behavior on the pyramid

Using `knowledge/test-pyramid.md`, assign each behavior to the lowest layer that can meaningfully verify it (unit / integration / component / contract / E2E). Flag anything currently mis-layered. For service boundaries, apply contract testing per `knowledge/microservice-testing.md` instead of E2E.

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
| Behavior | Layer | Why this layer |

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
