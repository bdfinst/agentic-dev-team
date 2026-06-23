---
name: domain-driven-design
description: Model software around the business domain. Use when designing bounded contexts, defining aggregates and value objects, mapping context relationships, or working with complex business logic. Apply before implementation to prevent model drift.
role: worker
user-invocable: true
---

# Domain-Driven Design (DDD)

## Overview

Model software around the business domain. Collaborate with domain experts to build a shared understanding expressed in code through ubiquitous language, bounded contexts, and tactical patterns.

## Strategic Patterns

### Ubiquitous Language

- Code, documentation, and communication all use the same domain terminology
- If the domain expert calls it an "enrollment," the code calls it `Enrollment`, not `Registration`
- Language inconsistencies signal a modeling problem

### Bounded Contexts

- Each context owns its own domain model with clear boundaries
- The same real-world concept may have different representations in different contexts
- A `Customer` in Billing is not the same model as a `Customer` in Shipping

### Context Mapping

Define explicit relationships between bounded contexts:

| Pattern | When to Use |
| --- | --- |
| **Shared Kernel** | Two contexts co-own a small, stable subset of the model |
| **Anti-Corruption Layer** | Protect your model from a messy or legacy external model |
| **Customer/Supplier** | Upstream context serves downstream; downstream can negotiate |
| **Conformist** | Downstream adopts upstream's model as-is (no negotiation power) |
| **Open Host Service** | Context exposes a well-defined protocol for many consumers |
| **Published Language** | Shared interchange format (e.g., industry standard schemas) |
| **Separate Ways** | No integration at all — the cheaper, more honest choice when the cost of integrating two contexts outweighs the benefit |

### Distillation — Find the Core Domain

Not all of the model is equally valuable. Spend your best modeling effort where it earns the most.

- **Core Domain** — the part that makes the business worth doing; your competitive advantage. Assign your strongest people here; invest in supple design.
- **Generic Subdomains** — necessary but undifferentiated (auth, notifications, currency conversion). Buy, adopt, or build plainly — do not gold-plate.
- **Supporting Subdomains** — business-specific but not differentiating. Build simply.
- **Domain Vision Statement** — a short paragraph naming the Core Domain and why it matters. Write it early; it directs investment and prioritization.

Misallocation is the smell: elaborate custom code in a generic subdomain, or an anemic, neglected Core.

## Tactical Patterns

### Aggregates

- Cluster of entities and value objects with a single **aggregate root**
- All external access goes through the root
- Enforce consistency boundaries: one transaction = one aggregate
- Keep aggregates small; reference other aggregates by ID, not by object

### Entities

- Defined by identity, not attributes
- Two entities with the same attributes but different IDs are different objects
- Track lifecycle and state changes

### Value Objects

- Defined by attributes, not identity
- Immutable; equality by value comparison
- Use for: money, addresses, date ranges, measurements

### Domain Events

- Record that something meaningful happened in the domain
- Named in past tense: `OrderPlaced`, `PaymentReceived`, `EnrollmentCompleted`
- Enable cross-context communication and eventual consistency
- Carry enough data for consumers to act without calling back

### Domain Services

- Operations that don't naturally belong to a single entity or value object
- Stateless; coordinate across multiple aggregates
- Example: `TransferFundsService` operating across two `Account` aggregates

### Repositories

- Domain-level abstraction for aggregate persistence
- Interface defined in the domain/application layer (a port)
- Implementation lives in the infrastructure/adapter layer
- One repository per aggregate root

### Factories

- Encapsulate complex creation of an aggregate or value object so the result is **valid and whole** the moment it exists
- Move construction invariants out of clients and out of overloaded constructors
- A factory belongs to the domain layer; it produces domain objects, it does not persist them
- Use when a constructor would have to know too much, or when creation enforces a non-trivial invariant
- Skip for objects that are valid by simple construction — a factory is overhead there

### Specifications

- Encapsulate a business rule as a first-class predicate object (`OverdueInvoiceSpecification`, `EligibleForDiscountSpecification`)
- Three uses: **validation** (does this object satisfy the rule?), **selection** (query for objects that match), **construction-to-order** (build an object that satisfies the rule)
- The tool for **making an implicit concept explicit**: when the same multi-clause boolean appears in several places, that duplicated predicate is a named domain rule wearing a disguise — give it a name and a type
- Compose specifications (and / or / not) rather than copying the condition

## Making Implicit Concepts Explicit

When a constraint, process, or policy is buried in conditionals and scattered across methods, the model is hiding a concept the domain expert already has a word for. Surface it:

| Hidden as | Surface it as |
| --- | --- |
| A repeated multi-clause `if` | A **Specification** or **Policy** object |
| A constraint enforced ad hoc in setters | An invariant the **entity/aggregate** guards |
| A multi-step business process in a service method | A named **domain process** or sequence of **domain events** |
| A primitive that always travels with rules (`int balanceCents`) | A **Value Object** (`Money`) that owns those rules |

## Supple Design

The craft of refactoring toward deeper insight — design that is safe to change because it reveals intent and contains side effects. Apply to the Core Domain especially.

- **Intention-Revealing Interfaces** — name classes and methods for *what* they accomplish, not how; a caller should not need to read the implementation. Boolean flag parameters that switch behavior are a smell.
- **Side-Effect-Free Functions** — push computation into functions that return results without changing state; keep state changes in a small, obvious set of command methods (command-query separation). Value Objects should expose only side-effect-free operations.
- **Assertions** — state post-conditions and invariants explicitly (in code or tests) so behavior is guaranteed, not inferred from reading the body.
- **Conceptual Contours** — factor the model along the domain's own seams so that what changes together lives together; a single conceptual change should touch one place.
- **Standalone Classes** — drive down dependencies so a class can be understood and tested in isolation; low coupling is the goal, not just clean layering.
- **Closure of Operations** — where it fits, define operations whose argument and result are the same type (`Money.add(Money) → Money`); they compose without dragging in other concepts.

## Knowledge Crunching & Model-Driven Design

- The model is not designed up front and frozen — it emerges from **continuous collaboration with domain experts**, distilling messy reality into sharp abstractions.
- **Bind the model to the implementation.** If the code drifts from the model the team talks about, the model is fiction. The same terms, the same relationships, in conversation and in code.
- Expect **breakthroughs**: periodic refactorings where a better abstraction suddenly clarifies a whole area. Leave room for them; they are the payoff of crunching, not a failure of earlier design.

## When to Apply

| Situation | Approach |
| --- | --- |
| Complex, evolving business logic | Full tactical DDD (aggregates, events, services) |
| Simple CRUD with minimal logic | Skip tactical patterns; use DDD strategically (bounded contexts, ubiquitous language) |
| Legacy integration | Anti-Corruption Layer to protect new model |
| Multiple teams / services | Context mapping is essential |

## Steps

### 1. Establish Ubiquitous Language

- Identify domain terms from requirements and stakeholder input
- Verify code uses the same terms as domain experts
- Flag language inconsistencies between code, docs, and conversation

### 2. Define Bounded Contexts

- Map each distinct model to its own context with clear boundaries
- Identify context relationships using context mapping patterns (Shared Kernel, ACL, etc.)

### 3. Distill the Core

- Classify each subdomain as Core, Supporting, or Generic; write a one-paragraph Domain Vision Statement for the Core
- Direct the strongest modeling effort (and supple design) at the Core; keep Generic subdomains plain

### 4. Select Tactical Patterns

- Determine whether the domain complexity warrants aggregates, entities, value objects, factories, specifications, and domain events
- For simple CRUD, apply strategic DDD only (contexts + language)

### 5. Validate Model

- Confirm aggregates enforce consistency boundaries (one transaction = one aggregate)
- Confirm cross-context communication uses domain events, not direct references
- Confirm repositories exist per aggregate root with interfaces in domain/application layer
- Confirm objects are valid on creation (constructor or factory), and that named business rules are explicit (specifications/policies), not duplicated conditionals

## Output

Report modeling decisions: bounded contexts identified, aggregate boundaries, context map relationships, and any violations of DDD constraints found in existing code. Be concise — use tables for context maps and violation lists; skip concept narration.

## Constraints

- Do not share aggregate instances across bounded contexts; reference by ID only
- Do not leak domain model internals through API boundaries
- Do not apply full tactical DDD to simple CRUD domains

## Guidelines

- Start with strategic DDD (contexts, language) before reaching for tactical patterns
- Not every service needs aggregates; recognize when simpler models suffice
- Domain events are the primary mechanism for cross-context communication
- Aggregates define transaction boundaries, not query boundaries (use read models for queries)
- Validate ubiquitous language continuously; stale language leads to model drift
- Reserve supple design (intention-revealing interfaces, side-effect-free functions, specifications) for the Core Domain; over-engineering a generic subdomain is its own smell
- A repeated multi-clause condition is an implicit concept — name it (specification/policy) rather than copying it
