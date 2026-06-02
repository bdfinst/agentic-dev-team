---
name: design-it-twice
description: >-
  Generate multiple radically different interface designs for a module using
  parallel sub-agents, then compare and synthesize. Based on Ousterhout's
  "Design It Twice" principle. Use when the user wants to explore interface
  options, design an API, compare module shapes, or says "design it twice",
  "what are my options", or "show me alternatives". Also use when the Architect
  agent is designing a new module boundary or public interface.
role: worker
user-invocable: true
---

# Design It Twice

## Overview

Your first design idea is rarely your best. This skill generates multiple radically different interface designs for a module by dispatching parallel sub-agents with divergent constraints, then compares them so the user can make an informed choice. Based on "Design It Twice" from John Ousterhout's *A Philosophy of Software Design*.

This skill is about **interface shape**, not implementation. Don't write code — design the contract.

## When to Use

- Designing a new module, service, or API boundary
- Refactoring an existing interface that feels wrong
- Any time there's a non-obvious choice about how to expose functionality
- When the Architect agent identifies a new module boundary during planning

## Process

### 1. Gather Requirements

Before designing, understand the constraints:

- What problem does this module solve?
- Who are the callers? (other modules, external users, tests)
- What are the key operations?
- What should be hidden inside vs exposed?
- Any hard constraints? (performance, compatibility, existing patterns in the codebase)

Explore the codebase to find existing patterns and conventions. Ask the user only for what you can't determine from the code.

### 2. Generate Designs (Parallel Sub-Agents)

Spawn 3+ sub-agents simultaneously using the Agent tool. Each must produce a **radically different** approach — not variations on a theme.

Assign each agent a different design constraint:

| Agent | Constraint | Optimizes for |
|-------|-----------|---------------|
| 1 | "Minimize the interface — aim for 1-3 methods max" | Simplicity, deep module |
| 2 | "Maximize flexibility — support many use cases and extension" | Generality, future-proofing |
| 3 | "Optimize for the most common caller — make the default case trivial" | Ergonomics, productivity |
| 4 | (optional) "Design around ports & adapters for cross-boundary deps" | Testability, isolation |

Each sub-agent produces:
1. **Interface signature** — types, methods, parameters
2. **Usage example** — how a real caller would use it
3. **What it hides** — complexity kept internal
4. **Trade-offs** — what you gain and what you give up

### 3. Present Designs

Show each design sequentially so the user can absorb one before seeing the next. Don't use comparison tables for the designs themselves — prose is better for understanding trade-offs.

### 4. Compare

After presenting all designs, compare them on these dimensions:

- **Interface simplicity**: fewer methods and simpler params = easier to use correctly
- **Depth**: small interface hiding significant complexity (good) vs large interface with thin implementation (bad)
- **Ease of correct use** vs **ease of misuse**
- **Implementation efficiency**: does the interface shape allow efficient internals?
- **Testability**: can callers test against this interface without mocking internals?

Give your own recommendation — which design is strongest and why. If elements from different designs would combine well, propose a hybrid. Be opinionated.

### 5. Synthesize

Ask the user:
- "Which design best fits your primary use case?"
- "Any elements from other designs worth incorporating?"

The final design often combines insights from multiple options.

## Anti-Patterns

- Don't let sub-agents produce similar designs — enforce radical difference via constraints
- Don't skip the comparison step — the value is in the contrast
- Don't implement — this is purely about interface shape
- Don't evaluate based on implementation effort — that's a separate concern
