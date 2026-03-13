# Domain Modeling Patterns

Reference file for the domain-review agent. Read this before starting
analysis to apply DDD assessment patterns.

## Exploration Patterns

Map the project structure before detecting issues.

### Entity / Model discovery

| Glob pattern | What it finds |
|--------------|---------------|
| `**/domain/**`, `**/entities/**`, `**/models/**`, `**/aggregates/**` | Domain layer |
| `**/services/**`, `**/application/**`, `**/usecases/**`, `**/handlers/**` | Application layer |
| `**/repositories/**`, `**/dal/**`, `**/persistence/**`, `**/infrastructure/**` | Data access layer |
| `**/dto/**`, `**/dtos/**`, `**/responses/**`, `**/contracts/**`, `**/api/**`, `**/viewmodels/**` | Transfer objects |

### ORM marker detection

| Language | Grep patterns |
|----------|---------------|
| JS/TS | `@Entity`, `@Table`, `@Column`, `@Document` |
| C# | `[Table]`, `[Key]`, `[Column]`, `DbContext`, `DbSet<` |
| Java | `@Entity`, `@Table`, `@MappedSuperclass`, `@Repository` |

### Boundary entry point detection

| Language | Grep patterns |
|----------|---------------|
| JS/TS | `express`, `fastify`, `Request, Response` |
| C# | `ControllerBase`, `[ApiController]`, `IActionResult` |
| Java | `@RestController`, `@Controller`, `@RequestMapping` |

### Application service detection

| Language | Grep patterns |
|----------|---------------|
| JS/TS | `@Injectable`, `@Service`, class names ending in `Service` |
| C# | Class names ending in `Service`, `Handler`, `UseCase` |
| Java | `@Service`, `@Component`, class names ending in `Service`, `Handler` |

If none of these patterns yield files, return skip.

## Anti-Pattern Recognition

### Business Logic Misplacement

Logic belongs in the domain layer. Flag when found in:

| Wrong location | Signal |
|---------------|--------|
| Controllers/routes | Discount calculations, validation rules, authorization logic in route handlers |
| Repositories/DAL | Business rules in SQL queries, computed columns, trigger-like logic |
| Application services | Rules that should be on an entity or domain service (application services orchestrate, they don't own rules) |

Exception: domain services legitimately own rules that span multiple entities.

### Anemic Domain Model

Entities that are pure data holders (only getters/setters) while services
contain all behavior. Signs:

- Entity has 10+ properties but 0 methods beyond accessors
- Service methods that take an entity, inspect its state, and return a decision
- External callers setting status fields directly instead of calling intention-revealing methods (`order.status = 'paid'` vs `order.markPaid()`)

### Abstraction Leaks

| Leak type | Signal |
|-----------|--------|
| ORM in domain | Domain objects with `@Column`, `[Table]`, persistence annotations |
| HTTP in domain | Domain objects importing `Request`, `Response`, HTTP status codes |
| Infrastructure in domain | Domain layer importing database clients, message queues, file I/O |

### Boundary Violations

| Violation | Signal |
|-----------|--------|
| Missing DTOs | Domain entities returned directly from API endpoints |
| Cross-context coupling | Direct imports between bounded contexts instead of events/shared kernel |
| Aggregate boundary bypass | Reaching into an aggregate's child entities directly |

### Ubiquitous Language Drift

Flag only internal inconsistency observable in code:

- Same concept with different names across modules (`Order` / `Purchase` / `Transaction`)
- Generic names where domain terms exist (`process`, `handle`, `data`, `info`, `manager`)

Do not flag terminology as wrong based on assumed business language.
