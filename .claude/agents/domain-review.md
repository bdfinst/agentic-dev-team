---
name: domain-review
description: Domain boundaries, abstraction leaks, business logic placement
tools: Read, Grep, Glob
model: opus
---

# Domain Review

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=clean model, warn=minor issues, fail=boundary violations
Severity: error=violation that causes data exposure, cross-context coupling, or untestable code; warning=misplaced logic or missing abstraction that adds friction; suggestion=modeling improvement with no immediate harm
Confidence: high=mechanical (add missing DTO, rename to domain term); medium=direction clear, entity/service split may have tradeoffs; none=requires human judgment (aggregate boundary decisions, bounded context design)

Model tier: frontier
Context needs: project-structure

## Explore

Before detecting issues, map the project structure:

1. Glob for entity/model files: `**/domain/**`, `**/entities/**`, `**/models/**`, `**/aggregates/**`
2. Glob for service files: `**/services/**`, `**/application/**`, `**/usecases/**`, `**/handlers/**`
3. Glob for repository/data-access files: `**/repositories/**`, `**/dal/**`, `**/persistence/**`, `**/infrastructure/**`
4. Glob for DTO/response files: `**/dto/**`, `**/dtos/**`, `**/responses/**`, `**/contracts/**`, `**/api/**`, `**/viewmodels/**`

Locate persistence-mapped classes by grepping for ORM markers:

- **JS/TS**: `@Entity`, `@Table`, `@Column`, `@Document`
- **C#**: `\[Table\]`, `\[Key\]`, `\[Column\]`, `DbContext`, `DbSet<`
- **Java**: `@Entity`, `@Table`, `@MappedSuperclass`, `@Repository`

Locate boundary entry points by grepping for framework markers:

- **JS/TS**: `express`, `fastify`, `from 'express'`, `Request, Response`
- **C#**: `ControllerBase`, `\[ApiController\]`, `IActionResult`, `Microsoft.AspNetCore`
- **Java**: `@RestController`, `@Controller`, `@RequestMapping`, `HttpServletRequest`

Locate application service layer by grepping for:

- **JS/TS**: `@Injectable`, `@Service`, class names ending in `Service`
- **C#**: class names ending in `Service`, `Handler`, `UseCase`
- **Java**: `@Service`, `@Component`, class names ending in `Service`, `Handler`, `UseCase`

If none of these patterns yield files, return skip.

## Skip

Return `{"status": "skip", "issues": [], "summary": "No domain model to analyze"}` when:

- Target is infrastructure-only code (CI/CD, build scripts, configs)
- No business logic or domain entities present

## Detect

Business logic placement:

- Business rules in UI/controller layer (route handlers computing discounts, validation, authorization)
- Business rules in repository or data-access layer
- Application services containing business rules — application services should orchestrate domain objects and infrastructure, not own rules; flag business logic that belongs on an entity or domain service
- Note: domain services legitimately own business rules that don't belong to a single entity — do not flag these

Abstraction leaks:

- Domain objects exposing implementation details
- Technical concerns in domain model
- Infrastructure code (DB, HTTP) mixed with domain

Entity/DTO confusion:

- Missing DTOs for cross-boundary transfer
- Domain objects used for data transfer

Boundary violations:

- Aggregate boundaries not respected
- Direct cross-context dependencies
- Missing domain events for cross-boundary communication

Ubiquitous language:

- Inconsistent terminology within the codebase for the same concept (e.g., `Order` in one module, `Purchase` in another, `Transaction` in a third with no clear distinction)
- Generic names that obscure intent (`process`, `handle`, `data`, `info`, `manager`) where a domain term would be more precise

Note: do not flag terminology as wrong based on assumed business language — only flag internal inconsistency that is observable in the code.

Anemic domain model:

- Entities or aggregates that are pure data holders (only getters/setters, no behavior) while all logic lives in services — suggest moving invariant enforcement and state transitions onto the entity
- Entities that allow external callers to set internal state directly instead of through intention-revealing methods (e.g., setting a status field directly rather than calling a method like `markPaid()` or `Submit()`)

## Ignore

Code structure, naming style, tests (handled by other agents)
