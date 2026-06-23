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

### Implicit Concepts (missing Specification / Policy)

A named business rule hiding inside scattered conditionals. Surface it as a Specification or Policy object.

| Signal | What it implies |
|--------|-----------------|
| The same multi-clause boolean (`if a && b && !c`) duplicated in 2+ places | A domain rule with a name the experts already use — extract to a specification/policy object |
| A rule expressed as a comment (`// orders over $X to a new address need review`) but enforced ad hoc | The concept exists in language but not in the model |
| A boolean-returning method on a service that inspects another object's fields | Tell-don't-ask + a candidate specification owned by the domain |

Only flag duplication or comment-encoded rules you can point to. A single, local condition is not a missing specification.

### Construction Without Invariants (missing Factory)

| Signal | What it implies |
|--------|-----------------|
| Public constructor / object literal that lets a caller build an invalid aggregate (required field unset, two fields that must agree set independently) | Construction invariant is unenforced — a factory or a guarding constructor should make the object valid-on-creation |
| The same multi-step assembly of an aggregate repeated across call sites | Creation logic belongs in one factory, not copied into clients |

Do not flag simple objects that are valid by plain construction — a factory there is overhead.

### Supple Design Smells (domain model only)

Scope these to **domain entities, value objects, and domain services** — general purity/coupling elsewhere belongs to `js-fp-review` and `structure-review`, not here.

| Smell | Signal | Fix direction |
|-------|--------|---------------|
| Not intention-revealing | A domain method named for *how* not *what* (`recalc`, `doProcess`), or a boolean flag parameter that switches behavior (`price(true)`) | Rename to the domain verb; split the two behaviors |
| Side effect in a query | A method on a value object or entity that both mutates state and returns a value (violates command-query separation) | Separate the command from the query; value objects expose only side-effect-free operations |
| Mutable value object | A type used as a value (money, range, coordinate) with public setters or in-place mutation | Make it immutable; return new instances |
| Unenforced invariant | An entity/aggregate whose invariant is asserted by callers rather than guarded internally | Move the invariant into the type (constructor, factory, or guarded mutator) |

### Ubiquitous Language Drift

Flag only internal inconsistency observable in code:

- Same concept with different names across modules (`Order` / `Purchase` / `Transaction`)
- Generic names where domain terms exist (`process`, `handle`, `data`, `info`, `manager`)

Do not flag terminology as wrong based on assumed business language.
