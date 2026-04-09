---
name: legacy-code
description: Safely modify code that lacks tests. Use whenever tasked with changing code without test coverage — apply characterization tests and dependency-breaking techniques before making any behavioral changes.
role: worker
user-invocable: true
---

# Legacy Code

## Overview

Techniques for safely modifying code that lacks tests or has poor structure. Based on the principle that legacy code is code without tests (Michael Feathers' definition) — regardless of age. The goal is to get code under test before changing it, then improve structure incrementally.

## Constraints
- Never change behavior and structure in the same step; refactor under green tests only
- Write characterization tests before modifying legacy code — not after
- Prefer the smallest dependency break that gets code under test
- Do not apply aggressive refactoring without test coverage

## Core Concepts

### Legacy Code Definition
Code without tests. A well-structured 6-month-old codebase with no tests is legacy. A messy 10-year-old codebase with comprehensive tests is not. The presence or absence of tests determines whether you can change code safely.

### The Legacy Code Change Algorithm
1. **Identify change points** — where in the code does the change need to happen?
2. **Find test points** — where can you observe the effects of the change?
3. **Break dependencies** — make the code testable without changing its behavior
4. **Write tests** — characterization tests that lock down existing behavior
5. **Make changes and refactor** — now that tests protect you, modify behavior and improve structure

### Seams
A seam is a place where behavior can be altered without editing the code under test:
- **Object seams** — use polymorphism to substitute behavior (interfaces, subclasses)
- **Link seams** — substitute dependencies at the linking/import level (dependency injection, module mocking)
- **Preprocessing seams** — alter behavior via build configuration, feature flags, or compile-time substitution

### Characterization Tests
Tests that document what the code *actually does*, not what it *should do*. They lock down existing behavior so you can detect unintended changes. Characterization tests answer: "If I make a change here, what breaks?"

## Patterns

### Characterization Test Procedure
1. Find the code area you need to change
2. Write a test that calls the code and lets it fail to reveal actual output
3. Update the test assertion to match observed behavior
4. Repeat until the change area and its immediate dependencies are covered
5. Use these tests as a safety net — any behavioral change will now show as a test failure

### Dependency Breaking Techniques

| Technique | When to Use | Risk |
| --- | --- | --- |
| Extract Interface | Class has many dependencies you need to substitute | Low |
| Extract Method | Long method with embedded logic you need to isolate | Low |
| Parameterize Constructor | Class creates its own dependencies internally | Low |
| Subclass and Override Method | Need to neutralize or replace specific behavior in tests | Medium |
| Wrap Method | Adding behavior before/after existing method without modifying it | Low |
| Wrap Class (Decorator) | Adding behavior transparently to callers of existing class | Medium |
| Sprout Method | New behavior is clearly separable from existing method | Low |
| Sprout Class | New behavior requires its own state or complex logic | Medium |
| Adapt Parameter | Method depends on a type you can't use in tests | Medium |

### Sprout vs. Wrap Decision
- **Sprout** (new method/class called from existing code): use when the new behavior is an addition that existing code needs to invoke at a specific point. The existing code changes minimally — it gains one call to the new method.
- **Wrap** (new code that calls existing code): use when existing callers must see the new behavior transparently without modification. The new code sits between callers and the original code.

### Strangler Pattern
Incrementally replace legacy components by routing new behavior through new code while old code remains operational:
1. Identify a bounded area of legacy functionality
2. Build new implementation alongside the old
3. Route new requests/features through new code
4. Gradually migrate existing behavior to new code
5. Remove old code only when fully replaced and verified

## Output
Report the legacy code analysis: identified change points, test points, dependency breaks needed, characterization test targets, and the recommended refactoring sequence. Be concise — bullet list format; skip background explanation.

## When to Apply

| Situation | Apply? |
| --- | --- |
| Modifying code without tests | Yes |
| Adding behavior to poorly structured code | Yes |
| Migrating legacy components to new architecture | Yes |
| Greenfield development | No |
| Code already well-tested and well-structured | No |
| Pure deletion of unused code | No |

## Guidelines

1. Never change behavior and structure in the same step. Refactor under green tests only.
2. Write characterization tests before modifying legacy code. The tests document current behavior, not desired behavior.
3. Prefer the smallest dependency break that gets code under test. Aggressive refactoring without test coverage creates risk.
4. Sprout when the new behavior is clearly separable; wrap when existing callers must see the new behavior transparently.
5. Every dependency break is temporary scaffolding — revisit and clean up once test coverage allows broader refactoring.
6. If you cannot find a seam, extract method first. Extract Method is the safest starting point for almost any dependency break.
7. Characterization tests are not a substitute for acceptance tests. They lock behavior; acceptance tests define behavior.

## Integration

- **[Specs](../specs/SKILL.md)** — when modifying legacy code to add new behavior, specify the new behavior first, then use this skill to get existing code under test before implementing
- **[Hexagonal Architecture](../hexagonal-architecture/SKILL.md)** — dependency breaking techniques move legacy code toward port/adapter separation incrementally
- **[Quality Gate Pipeline](../quality-gate-pipeline/SKILL.md)** — verify characterization tests match observed behavior (Phase 1); legacy code changes have higher defect risk, apply review-correction with increased scrutiny (Phase 3)
- **[Mutation Testing](../mutation-testing/SKILL.md)** — after writing characterization tests, use mutation testing to verify those tests catch behavioral changes
