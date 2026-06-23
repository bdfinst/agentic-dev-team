# Architecture Assessment Patterns

Reference file for the arch-review agent. Read this before starting
analysis to apply architectural compliance patterns.

## Exploration Patterns

Map the architectural landscape before detecting issues.

### Discovery sequence

1. **ADRs**: Glob for `**/adr/**`, `**/adrs/**`, `**/decisions/**`, `docs/adr*`
2. **Architecture docs**: Glob for `docs/architecture.md`, `docs/arch*.md`, `ARCHITECTURE.md`, `README.md`
3. **Layer definitions**: Glob for `**/domain/**`, `**/application/**`, `**/infrastructure/**`, `**/presentation/**`, `**/api/**`, `**/ui/**`
4. **Import patterns**: Grep for cross-layer imports

If no architecture documentation and no discernible layered structure exists, return skip.

## ADR Compliance Checks

| Check | How to detect |
|-------|---------------|
| Prohibited library | ADR says "do not use X"; code imports X |
| Mandated pattern bypass | ADR requires event sourcing/hexagonal ports; code uses direct calls |
| Unreflected reversal | ADR decision reversed in code but ADR status not `Superseded` |

## Layer Boundary Rules

Standard layered architecture enforces dependency direction:
`presentation → application → domain ← infrastructure`

| Violation | Signal |
|-----------|--------|
| Infrastructure → Domain | ORM entity imported by domain service |
| Domain → Application | Domain layer importing application service types |
| Domain → Infrastructure | Domain importing database clients, HTTP clients |
| Presentation → Domain direct | UI importing domain internals, bypassing use cases |
| Cross-context direct | One bounded context importing domain types from another |

Flag: the specific import statement, source file, target file, and which boundary is crossed.

## Dependency Direction Checks

| Check | Signal |
|-------|--------|
| New circular dependency | Module A imports B, B imports A (where previously unidirectional) |
| Leaf node violation | A utility/shared module now depends on core business logic |
| Unwrapped third-party | Third-party library used directly in domain/application layer without interface |

## Pattern Consistency Checks

Flag when new code diverges from established patterns for the same concern:

| Concern | Inconsistency signal |
|---------|---------------------|
| Data access | Repository pattern used elsewhere, direct DB access in new code |
| Cross-context communication | Events used elsewhere, direct calls in new code |
| Error handling | Result types used elsewhere, exceptions in new code (or vice versa) |
| Duplicate abstractions | Two repository base classes, two HTTP client wrappers |

## Prohibited Practice Detection

Grep for patterns that architecture docs explicitly ban:

| Pattern | When prohibited |
|---------|----------------|
| `new` infrastructure objects in domain | If docs prohibit constructor coupling |
| Direct `fetch`/`axios`/`HttpClient` outside adapter layer | If docs mandate HTTP abstraction |
| Direct DB client calls outside repository layer | If docs mandate repository pattern |

## Database Change Safety

When the changeset includes schema migrations or DDL, a change must keep every release deployable and reversible. Fuller treatment: `knowledge/database-change-management.md`.

| Signal | Risk | Fix direction |
|--------|------|---------------|
| `DROP`/`RENAME` of a column/table the same release's app still reads or writes | Breaks running instances mid-rollout; blocks rollback | Split into expand/contract across releases (add new, dual-write, switch reads, drop later) |
| Roll-forward migration with no paired roll-back script | The release cannot be rolled back | Author and test the reversal |
| New `NOT NULL` column or constraint added without a backfill step | Migration fails or long-locks on real data | Add nullable → backfill → enforce in a later release |
| App code and schema assumed to deploy atomically | Old app instances error mid-rollout | Make the change backward-compatible (expand first) |
| Manual SQL in a runbook instead of a versioned migration script | No audit trail; not reproducible; drifts across environments | Move into a versioned migration in version control |

Flag the migration file and the coupled application code. Scope to migration/DDL changes only; ordinary data-access code is out of scope here.

## MCP-Enhanced Analysis

If a code knowledge graph MCP is available (e.g., GitNexus):

| Tool | Purpose |
|------|---------|
| `list_repos` | Discover ecosystem — what other repos exist |
| `query` | Map cross-repo dependencies — who calls this service |
| `context` | 360-degree view of key entry points |
| `impact` | Quantify blast radius of architectural changes |

Fall back to local Grep/Read if unavailable.
