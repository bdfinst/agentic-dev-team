---
name: api-design
description: Contract-first API design patterns for defining stable, evolvable interfaces
role: worker
user-invocable: true
---

# API Design

## Overview

Contract-first API design patterns for defining stable, evolvable interfaces between system components. Protocol-agnostic — applies to REST, gRPC, GraphQL, message-based, or any other interface style.

## Constraints
- Define the contract before implementing it; implementation conforms to the contract
- Every endpoint must have an error contract; unspecified failure modes are not acceptable
- Never remove a field or endpoint without a deprecation period and migration path
- Do not expose internal domain models directly through API boundaries

## Core Concepts

### Contract-First Design

Define the interface before implementing it. The contract is the source of truth; implementation conforms to the contract, not the other way around. Contracts are versioned artifacts.

### Resource Modeling

- **Entities** — individual resources with identity (e.g., `/orders/{id}`)
- **Collections** — groups of entities with filtering, pagination, sorting
- **Relationships** — links between resources expressed through references or embedding
- **Operations** — actions on resources (CRUD and domain-specific operations)

### Versioning Strategies

| Strategy | Mechanism | Trade-offs |
| --- | --- | --- |
| URL path | `/v1/resources`, `/v2/resources` | Simple routing, but proliferates endpoints |
| Header | `Accept: application/vnd.api.v2+json` | Clean URLs, but harder to test and discover |
| Content negotiation | Media type with version parameter | Standards-compliant, but adds client complexity |

Choose one strategy per API boundary and apply it consistently. URL path versioning is the simplest default.

### Error Contracts

Every API defines structured error responses:

| Field | Purpose |
| --- | --- |
| Error code | Machine-readable identifier (stable across versions) |
| Message | Human-readable description |
| Correlation ID | Trace identifier linking request to logs |
| Details | Optional structured context (field-level validation errors, etc.) |

Error contracts are part of the API contract — not an afterthought.

## Patterns

### API Design Procedure

1. **Identify consumers** — who calls this API, what do they need, what are their constraints
2. **Define resources** — model the domain entities and relationships exposed through the interface
3. **Specify operations** — define actions on each resource with request/response shapes
4. **Define error cases** — enumerate failure modes with error codes and response structures
5. **Document constraints** — rate limits, pagination defaults, size limits, authentication requirements
6. **Choose version strategy** — select and document the versioning approach

### Backward Compatibility Checklist

| Change Type | Impact | Action |
| --- | --- | --- |
| Add optional field | Safe (additive) | No version bump needed |
| Add new endpoint | Safe (additive) | No version bump needed |
| Remove field | **Breaking** | Deprecate first, remove in next major version |
| Change field type | **Breaking** | New version required |
| Change endpoint URL | **Breaking** | Redirect old URL, new version |
| Tighten validation | **Breaking** | New version required |
| Loosen validation | Safe (relaxing) | No version bump, document change |

### Contract Validation

Before implementation begins, verify the API contract against:

- [ ] BDD scenarios cover all operations and error cases
- [ ] Acceptance criteria include non-functional requirements (latency, throughput)
- [ ] Consumer needs are met without exposing internal implementation details
- [ ] Error codes are unique and documented
- [ ] Versioning strategy is declared and consistent

## When to Apply

| Scenario | Apply? | Depth |
| --- | --- | --- |
| New external or public API | Yes | Full procedure |
| New inter-service boundary | Yes | Full procedure |
| Internal module boundary | Partially | Resource modeling and error contracts |
| Private helper functions | No | — |
| Modifying existing API contract | Yes | Backward compatibility checklist |

## Guidelines

1. **Design for consumers, not implementations.** The API shape reflects what callers need, not how the backend is structured.
2. **Every endpoint has an error contract.** Callers must know what failures look like before they write integration code.
3. **Deprecation before removal.** Never remove a field or endpoint without a deprecation period and migration path.
4. **Contracts are versioned artifacts.** Treat API contracts with the same rigor as source code — reviewed, versioned, and tested.
5. **Avoid leaking internal models.** Domain entities exposed through an API may need a separate representation (DTO/view model) to prevent tight coupling.
6. **Pagination is not optional for collections.** Unbounded collection responses are a reliability risk.

## Output
API contract document covering resources, operations, error cases, versioning strategy, and the backward compatibility checklist results. Be concise — use tables; skip narrative prose.

## Integration

- **Agent-Assisted Specification** — API contracts emerge during the Architecture Specification stage; validate them as part of the consistency gate
- **Hexagonal Architecture** — API contracts define the ports; adapters implement the protocol-specific translation
- **Domain-Driven Design** — API boundaries often align with bounded context interfaces; use context maps to identify integration points
