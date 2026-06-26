# Design Smells

Reference file for structure-review, complexity-review, and naming-review agents. Use the smell → pattern table to make findings actionable: every finding should name the smell, quote the code, name the remediation pattern, and include a refactor sketch.

---

## Design Smells → Pattern Mapping

| Smell | Signature in code | Remediation pattern |
|---|---|---|
| **Switch on type discriminator** | `switch (type) { case A: ...; case B: ...; }` or `if (x is A) ... else if (x is B) ...` repeated across multiple methods | **Replace Conditional with Polymorphism** → Strategy (behavior-driven) or State (lifecycle-driven) |
| **If/else cascade on type/state** | Same shape as above in `if`/`elif` form | Same: Replace Conditional with Polymorphism |
| **Long parameter list** | Function with 5+ parameters; reader can't recall positional meanings | **Introduce Parameter Object** — bundle related params into a named request/options type |
| **Data clumps** | Same group of 3+ parameters or fields travels together everywhere (`firstName, lastName, dob`) | **Extract Class / Value Object** — the clump is an unnamed concept |
| **Primitive obsession** | Business concepts modeled as raw strings/numbers (`string customerId`, `int amount`) | **Value Object** — typed wrapper with validation and equality |
| **Magic number / magic string** | Literals like `if (retries > 3)` or `if (status == "PND")` | **Replace Magic Literal** — extract named constant or enum; promote to Value Object when it carries business meaning |
| **Flag argument** | `process(true, false)` — boolean params that switch method behavior | **Split Method** — one method per branch; the flag is hiding two operations |
| **Long method** | Method >20 lines, often readable only with sub-section comments | **Extract Method** — each sub-section comment becomes a named method call |
| **Feature envy** | Method on class A reaches deeply into class B's data (`b.x.y.z`) | **Move Method** — relocate to class B where the data lives |
| **Shotgun surgery** | One conceptual change requires edits in 5+ unrelated classes | **Move Method / Move Field** — consolidate responsibility into one class |
| **Divergent change** | One class changes for many different reasons (auth, persistence, formatting) | **Extract Class** along the change axes — one class per reason-to-change |
| **Refused bequest** | Subclass overrides many parent methods to no-op or throw "not supported" | **Replace Inheritance with Composition** — the subclass needs *some* of the parent API; expose those via a member |
| **Speculative generality** | Abstract base classes or interfaces with only one implementation and no near-term plan for a second | **Inline Class** — collapse the abstraction; re-introduce when a second implementation appears |
| **Megaclass** | Class with 30+ public methods, multiple responsibilities, `*Manager`/`*Service`/`*Helper` suffix | **Extract Class** along responsibility lines; apply SRP |
| **Reinvented built-in / helper** | A hand-written loop or expression recomputes a standard-library operation (min, max, sum, copy, reverse, clamp) or duplicates a named helper that already exists in the module | **Use the platform** — replace with the built-in / existing helper so the algorithm reads top-down (see cheat-sheet below) |
| **Open-coded idiom** | The same non-trivial boolean or arithmetic expression (e.g. `Math.abs(x - y) > tol`) appears 3+ times inline instead of behind a named predicate | **Extract Method** — name the idiom (`withinTolerance`) so each call site states intent, not mechanics |

## Reinvented Built-in Cheat-Sheet

The "use the platform" smell is **language-agnostic** — recognize the *concept*
(a hand-rolled standard operation), then map it to the project's language. Flag
only as a `suggestion`; this is a readability call, not a correctness bug.

| Language | Hand-rolled → built-in (examples) |
|---|---|
| JS/TS | min/max scan → `Math.min(...xs)` / `Math.max(...xs)`; accumulator loop → `reduce`; `0 - x` → unary `-x`; copy loop → spread / `slice` |
| Python | min/max scan → `min()` / `max()`; accumulator loop → `sum()`; reimplemented `itertools` / `collections` helper |
| Java | loop → `Stream.min/max`, `Collectors`, `Math.max` |
| C# | loop → LINQ `Min` / `Max` / `Sum` / `Aggregate` |
| Go | loop → `min` / `max` **built-ins (Go 1.21+ only)**, `slices` / `maps` packages |

### What NOT to flag (reinvented built-in)

- A manual min/max (or similar) loop in a language/version that lacks the
  built-in — e.g. **Go before 1.21** has no `min`/`max`; the loop is idiomatic.
  Confirm the built-in exists for the project's language *and version* first.
- A hand-rolled form with a comment or context marking it a deliberate hot-path
  optimization (avoiding intermediate allocation, the spread argument-count
  limit, etc.) — confidence `none`, do not flag.
- C or other environments with no standard library for the operation.

## What NOT to Flag

- A `switch` over a closed enumeration where adding a case is rare (e.g., `DayOfWeek`, `HttpMethod`) — polymorphism adds ceremony without benefit
- A method whose extraction would only add a name without reducing cognitive load
- A 6-parameter constructor in a DI-injected class where all 6 are collaborators (not data clumps) — Parameter Object applies to *data* clumps, not dependency lists
- Speculative generality concerns on code that *will* gain a second adapter this sprint (per the team's roadmap)

---

## Finding Format

When surfacing a design smell as a finding:

```
Severity: error (blocks testing or hides a bug) | warning (impedes change) | suggestion (stylistic)
Smell: <smell name from table above>
File: path/to/file.ext:LINE
Code: <2-5 line quote of actual code>
Pattern: <recommended pattern>
Fix: <refactor sketch — 1-3 sentences on what the change looks like>
```

---

## Naming Offender Catalog

### Abbreviations that obscure intent

| Offender | Fix | Notes |
|---|---|---|
| `getEffDate` | `getEffectiveDate` | `Eff` is an internal abbreviation |
| `calcAmt` | `calculateAmount` | Two abbreviations + missing what amount |
| `OrderMgr` | `OrderRepository` or `OrderShippingService` | `Mgr` is vacuous — replace with the actual role |
| `tmpResult` | `intermediateTotal` | `tmp` reveals nothing about what it holds |
| `proc` / `Proc` | `processor` / `PaymentProcessor` | Spell out domain roles |
| `m_orderId` / `g_orderId` | `_orderId` (private) / `orderId` (local) | Hungarian prefix residue |

### Generic verbs that hide intent

| Offender | Fix | Reason |
|---|---|---|
| `processOrder` | `submitOrder` / `confirmOrder` / `cancelOrder` | "Process" hides which lifecycle step |
| `handleException` | `logAndSwallow` / `rethrowAsFault` / `retryWithBackoff` | "Handle" hides the actual policy |
| `doWork` | (the verb that names the work) | "Do" reveals nothing |
| `manage*` (`manageCart`, `manageInventory`) | Split into named operations: `addItem`, `removeItem` | "Manage" at class level is a smell; split into named methods |
| `update*` without qualifier | `markAsShipped` / `recordPayment` | "Update" hides which fields change and why |
| `execute` (outside Command/Strategy pattern) | The specific action | OK on `ICommand.execute()`; suspect elsewhere |

### Misleading names

| Offender | Why it misleads | Fix |
|---|---|---|
| `getCustomerOrThrow` returning null | Name says throw, code says null | Use `tryGetCustomer(out)` or actually throw |
| `isValid` that mutates state | "is" implies pure query | Split: `validate()` (mutates) + `isValid` (pure) |
| `save()` that may no-op | Name implies always-persists | `persistIfDirty()` or `flushPendingChanges()` |
| `cancel*` that emits an event but doesn't cancel state | Misnamed | `requestCancellation()` |

### Type-encoded names

| Offender | Fix |
|---|---|
| `stringList`, `intCount`, `boolIsActive` | `names` / `list`, `count`, `isActive` |
| `ICustomerInterface`, `OrderClass` | `ICustomer`, `Order` |

### What NOT to flag

- Loop counters: `i`, `j`, `k` are conventional
- Lambda parameters with single use: `x => x.id` doesn't need `customer => customer.id`
- Industry-standard acronyms: `HttpClient`, `XmlReader`, `JsonSerializer`, `SqlConnection`, `JWT`
- Domain-standard acronyms defined in the project's glossary (`.plans/domain/`)
- Test method names following `MethodName_Scenario_ExpectedResult` convention
