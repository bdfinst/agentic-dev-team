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

### 3. Select Tactical Patterns
- Determine whether the domain complexity warrants aggregates, entities, value objects, and domain events
- For simple CRUD, apply strategic DDD only (contexts + language)

### 4. Validate Model
- Confirm aggregates enforce consistency boundaries (one transaction = one aggregate)
- Confirm cross-context communication uses domain events, not direct references
- Confirm repositories exist per aggregate root with interfaces in domain/application layer

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
