---
name: domain-analysis
description: Strategic DDD health assessment of an existing system. Use whenever someone asks to analyze their architecture, assess domain health, find coupling problems, map bounded contexts, trace event flows across services, or understand what is slowing down delivery. Trigger on phrases like "what's wrong with our architecture", "where is the coupling", "assess our domain", "event storming", "value stream", "friction report", "bounded contexts", or "why is everything so tangled". Apply to existing codebases — use domain-driven-design skill for greenfield modeling.
role: worker
user-invocable: true
---

# Domain Analysis

## Overview

Assess the domain health of an existing multi-component system. Produce a structured report covering bounded context boundaries, context map relationships, domain event flows, value stream throughput, and a friction report identifying where the architecture inhibits continuous delivery.

This skill is analytical, not prescriptive. It describes what *is*, not what should be built. For greenfield design, use `skills/domain-driven-design.md`. For code-level violations (anemic model, missing DTOs, wrong layer), use `agents/domain-review.md`.

## Scope

Before starting, determine scope from the user's request:
- **Single repo**: analyze folder structure, package boundaries, shared models
- **Multi-repo / microservices**: analyze service boundaries, shared libraries, event contracts, API dependencies

## Evidence requirement

Every finding must be grounded in something you actually read. When reporting a God Object, a missing ACL, a coupling trap, or a friction item, cite the specific `file:line` or `file` where the evidence was observed. Do not assert that a pattern exists based on naming conventions alone — open the file and confirm it.

Classify each finding by confidence:
- **observed** — directly visible in a file you read (an import statement, a shared type, a method call)
- **inferred** — visible at folder or module level without reading implementation (directory name, package dependency in package.json)
- **suspected** — requires runtime knowledge or cannot be confirmed from static analysis alone

## Analysis Framework

### 1. Bounded Context Identification

Start here — structure reveals intent without reading implementation. Look at folder names, module names, and package boundaries first, then confirm with data schemas.

- Derive contexts from top-level folders, packages, or service names
- Flag **God Objects**: types that appear in multiple components under different meanings (e.g., `User` in Auth, Orders, and Billing with diverging fields) — these signal missing context boundaries
- Identify whether each context owns its model exclusively or borrows from neighbors
- A God Object is only a problem if its semantics diverge across contexts; the same name with the same meaning is fine

### 2. Context Mapping

For each inter-context relationship, classify the integration pattern. This matters because the pattern determines who can change what without coordinating with a neighbor.

| Pattern | Signal in code |
| --- | --- |
| **Anti-Corruption Layer** | Translator/mapper class at the boundary; explicit model conversion |
| **Shared Kernel** | Shared library or package co-owned by two contexts |
| **Customer/Supplier** | Downstream negotiates with upstream via contracts or versioned APIs |
| **Conformist** | Downstream uses upstream's model with no translation |
| **Open Host Service** | Published protocol (REST, gRPC, event schema) consumed by many |

Flag missing ACLs: direct dependencies between contexts that pass domain objects across boundaries without translation. These are the highest-risk coupling points — a schema change in one context silently breaks another.

### 3. Behavioral Event Storm

Domain events are the seams that let contexts evolve independently. Missing events are missing seams.

- Identify Domain Events: past-tense named events (`OrderPlaced`, `InventoryReserved`) crossing component boundaries
- Trace each event: which component emits it, which consume it, and whether consumers react synchronously or asynchronously
- Flag events that are missing (cross-boundary state changes with no event) or implicit (direct method calls that should be events)

### 4. Value Stream Flow

Trace a single unit of value through the system. Begin from a specific entrypoint you can point to in the code (e.g., a CLI command, an HTTP handler, a message consumer) — name it explicitly. Do not construct a hypothetical flow; trace the actual one.

- Identify the happy path: ordered sequence of component handoffs from entrypoint to outcome
- Flag synchronous handoffs where async would decouple the components (latency and availability risk)
- Flag handoffs with high coupling: caller must know too much about the downstream component's internals
- Identify missing compensating actions for failure mid-stream (e.g., payment charged but order not created)

### 5. Coupling Trap Detection

Identify feedback loops and cascading-change risks — the architectural patterns that make every deploy a coordination exercise.

- **Circular dependencies**: Component A depends on B, B depends on A (directly or transitively)
- **Coupling traps**: a change to one component's domain model forces breaking changes in others — signals missing abstraction or a misplaced boundary
- **Shared mutable state**: two contexts writing to the same tables or caches without clear ownership

## Steps

1. Map bounded contexts from directory structure and naming conventions
2. Identify God Objects spanning multiple contexts — open files to confirm semantic divergence
3. Chart context relationships using the integration pattern table
4. Locate missing ACLs by reading import statements across context boundaries
5. Run the event storm: list events, emitters, and consumers
6. Identify the value stream entrypoint in code; trace the happy path step by step
7. Identify coupling traps and circular dependencies
8. Write the Friction Report

## Output

### Bounded Contexts

Table: context name, owning file/package, primary aggregate or concern, upstream/downstream relationships.

### God Objects

List each: type name, contexts it appears in, diverging semantics, evidence (`file:line`). Omit types that appear in multiple places with consistent meaning.

### Context Map

Table of context relationships and their integration patterns. Flag missing ACLs with ⚠ and cite the import or call that crosses the boundary without translation.

### Domain Event Inventory

Table: event name, emitting context, consuming contexts, sync/async. If no domain events exist, say so explicitly — do not omit the section.

### Value Stream

State the entrypoint (file and function/command). Then list the ordered handoffs with coupling severity (low / medium / high) and confidence tier.

### Friction Report

Each item: category tag, specific files/components involved, confidence tier, and a concrete fix direction. Use this format:

```
[category] file-a → file-b (confidence: observed)
Description of the coupling or gap.
Fix: <specific action, e.g., "introduce ACL", "extract context", "replace sync call with domain event">
```

Categories: `deployment-coupling` | `data-coupling` | `semantic-coupling` | `event-gap`

**Example:**
```
[semantic-coupling] output.ts → enricher.ts (confidence: observed, output.ts:3)
output.ts imports classifyDDD() from enricher.ts — business logic that runs at render time
belongs in the enrichment phase. This creates a reverse dependency: Output depends on
Enrichment internals.
Fix: run classifyDDD during enrichment and store results on contextMap.dddInsights;
output.ts reads the pre-computed field.
```

## Constraints

- Do not redesign. Describe what exists; note what is missing.
- Do not flag code-level violations — those belong to `agents/domain-review.md`
- Scope coupling trap findings to cross-context boundaries; intra-context coupling is out of scope
- **Do not reframe infrastructure as a domain.** CI/CD stages, Terraform modules, deploy scripts, and Makefiles are not bounded contexts or aggregates. If no application logic exists, the skip applies regardless of how the concern layers are labeled.

## Guidelines

- Start with folder/package structure before reading any code — structure reveals intended boundaries
- Friction Report items must cite the specific file (and line if possible) where the coupling is observable
- If the system has no domain model (pure infrastructure, scripts, configs, build tools), return a brief note — two to three sentences — explaining that and skip the full report. Do not produce an "operational domain" or "infrastructure domain" analysis in its place.
