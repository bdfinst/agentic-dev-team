# Testability Design Patterns

Reference file for test-review and structure-review agents. When flagging untestable code, use the patterns below to specify the required **production code change** — not a test workaround. Tests never hack around untestable designs; the design must change.

Core principle: if code can't be tested through its public API, the production code's design must change. Per Seemann: "The hallmark of a testable design is that it's also a good design."

---

## "I Can't Test This Class" Decision Flow

```
Can I construct the object with the values I need for the test?
│
├─ YES → Write the test using the public constructor.
│
├─ NO: it has private-set properties with no public constructor
│   └─ Add a constructor that accepts values directly.
│      For 5+ parameters: apply Test Data Builder (Pattern 2).
│
├─ NO: it only has a static factory that calls a real database/service
│   └─ Add a constructor alongside the factory.
│      The factory uses the constructor internally.
│
├─ NO: the method I need to verify is protected/private
│   └─ Extract the logic into a public method or invoke through the
│      public behavior that calls it.
│
└─ NO: it depends on a concrete class I can't replace
    └─ Extract an interface for what this class needs.
       Mock the interface in tests, wire the concrete in production.

Each NO branch requires a production code change. That IS the work.
```

> **Legacy code (no tests yet)?** Don't make the design change cold. First get the code under characterization tests using a *behavior-preserving* seam from [`dependency-breaking-techniques.md`](dependency-breaking-techniques.md), guided by effect/pinch reasoning in [`legacy-test-strategy.md`](legacy-test-strategy.md) — then refactor toward the target patterns below. The patterns here are the destination; those techniques are how you get there safely.

---

## Pattern 1: Constructor Injection (Replace Static Factories / Singletons)

**Problem**: A class creates its own dependencies internally — `new ConcreteService()`, `ServiceLocator.get(T)`, static calls. The production code can't be given test doubles.

**Solution**: Accept collaborators as constructor parameters. Static factories and singletons remain for production wiring; they delegate to the constructor internally.

```
// BEFORE — untestable
class OrderProcessor:
  def process(orderId):
    db = Database.getInstance()     // static singleton
    logger = new FileLogger()       // new-ed up
    ...

// AFTER — injectable
class OrderProcessor:
  constructor(db: IDatabase, logger: ILogger):
    self.db = db
    self.logger = logger

  def process(orderId):
    ...
```

**When to apply**: class instantiates its own collaborators; class has no constructor that accepts its dependencies; production code works but tests can't isolate the unit.

---

## Pattern 2: Test Data Builder

**Problem**: Domain objects with many properties are painful to construct in every test. Most tests only care about 1-2 properties.

**Solution**: A builder in the test project with sensible defaults and a fluent API.

```
// Builder lives in the test project
class OrderBuilder:
  customerId = "TEST-CUST"
  amount = 100
  status = "pending"

  withCustomer(id): self.customerId = id; return self
  withAmount(amt): self.amount = amt; return self
  withStatus(s): self.status = s; return self
  build(): return Order(customerId, amount, status)

// In tests — only set what the test cares about
order = new OrderBuilder().withStatus("cancelled").build()
```

**When to apply**: domain object has 5+ properties; multiple tests need variants of the same object; default values work for most tests.

---

## Pattern 3: Interface Extraction for Large Contexts

**Problem**: Classes depend on a large context object with many properties. Mocking the full context is impractical and fragile.

**Solution**: Extract an interface for what each consumer actually needs.

```
// BEFORE — consumer takes the whole context
class FileProcessor:
  constructor(context: ProcessingContext)  // 40-field object

// AFTER — consumer takes only what it needs
interface IFileProcessorContext:
  tempFilePath(): string
  isReprocess: bool
  fileNames: List<string>

class FileProcessor:
  constructor(context: IFileProcessorContext)
```

The full context class implements this interface. Tests mock only the interface.

**When to apply**: context has 30+ properties but any given consumer uses 5-10; creating a full context for each test is excessive.

---

## Pattern 4: Fake Data Generators (Test Data with Variation)

**Problem**: Tests need realistic but controlled test data across many scenarios.

**Solution**: A typed faker or factory in the test project that generates valid domain values.

```
// Instead of magic literals
order = new Order(customerId="ABC123", amount=150.00, ...)

// Use a generator that makes intent clear
order = OrderFaker.pending()
order = OrderFaker.withAmount(5000)
orders = OrderFaker.generateBatch(100)
```

**When to apply**: tests need multiple records with varied data; domain validation rules constrain acceptable values; tests should not use unexplained magic numbers.

---

## The Design-for-Testability seam family

Constructor Injection (Pattern 1) is the common case, but it is one of a named family of seams from *xUnit Test Patterns* Ch. 26. Pick by *how* the dependency reaches the SUT and *why* it's hard to test.

| Seam | The change | Use when | Cost |
| ------ | ----------- | ---------- | ------ |
| **Dependency Injection** (Pattern 1) | Pass collaborators in (constructor/setter) | You control construction and can thread the dependency through | Low; the default |
| **Dependency Lookup** | SUT asks a broker/service-locator for the collaborator; the test configures the broker | The DOC is buried deep and threading it through every caller would be messy (e.g. a Fake DB behind a service facade) | Medium; hides the dependency, but far easier to **retrofit onto legacy** code than DI |
| **Humble Object** | Extract logic out of a hard-to-instantiate shell into a plain, synchronously-testable object | Logic is trapped in a UI control, framework callback, thread, or transaction boundary | Medium; the shell becomes a thin adapter |
| **Test Hook** | Conditional `if (testing)` behavior baked into production code | **Last resort only** — nothing else can break the dependency | High; it *is* the Test Logic in Production smell |

---

## Pattern 5: Dependency Lookup (retrofit seam for legacy)

**Problem**: A collaborator is constructed deep inside the system and there's no clean path to pass a test double down from the test — wiring DI through every intermediate layer would be invasive.

**Solution**: The SUT requests its collaborator from a **component broker / service locator** instead of `new`-ing it. The test (or a Setup Decorator) configures the broker to hand back a double.

```
// Production wiring registers the real implementation
ServiceRegistry.register(IClock, SystemClock)

// SUT looks up rather than receiving
class ExpiryService:
  def isExpired(token):
    clock = ServiceRegistry.get(IClock)   // broker, not `new`
    ...

// Test reconfigures the broker, no constructor threading needed
ServiceRegistry.register(IClock, FakeClock(at="2026-01-01"))
```

**When to apply**: retrofitting tests onto legacy code where DI would touch too many call sites; a deep DOC (data-access layer, facade-backed service) you want to replace with a Fake for a whole test run. **Trade-off**: the dependency is no longer visible in the signature, and the broker is global state that each test must reset — keep DI the default and reach for lookup when threading is genuinely impractical.

---

## Pattern 6: Humble Object (rescue logic from untestable shells)

**Problem**: Meaningful logic lives inside an object that's expensive or impossible to instantiate in a unit test — a GUI control, a framework callback, an async worker/thread, a transaction-managing controller. The asynchronicity or framework coupling forces slow, nondeterministic tests, so the logic ends up untested.

**Solution**: Extract **all** the logic into a separate, plain object that's testable through synchronous calls. The original shell becomes a *humble* adapter that holds no logic — it just forwards framework calls to the testable object. The shell is so thin it needs no tests of its own.

```
// BEFORE — logic trapped in a UI/framework/thread shell
class OrderView(FrameworkWidget):
  def onSubmit():           // framework-invoked, hard to test
    ...validation + pricing + state transitions...

// AFTER — Humble shell + testable presenter
class OrderPresenter:       // plain object, fully unit-testable
  def submit(input) -> ViewModel: ...the real logic...

class OrderView(FrameworkWidget):
  def onSubmit():           // humble: no logic, just delegation
    self.render(self.presenter.submit(self.readInput()))
```

Named variations: **Humble Dialog** (UI logic → presenter), **Humble Executable** (logic out of a thread/active object), **Humble Transaction Controller** (the business method takes no responsibility for begin/commit, so a test can wrap it in a transaction and roll back — the prerequisite for Transaction Rollback Teardown in `database-test-patterns.md`).

**When to apply**: nontrivial logic in any component that's problematic to instantiate because it depends on a framework, a UI toolkit, a thread, or a transaction. This is the production-code answer to the *Minimize Untestable Code* principle.

---

## Pattern 7: Test Hook (last resort — prefer any seam above)

**Problem**: None of the above seams can be introduced (e.g. a closed dependency that can't be injected, looked up, or subclassed), yet the code must be brought under test.

**Solution**: A conditional in production code that alters behavior under test. **This is deliberately listed last because it *is* the Test Logic in Production smell** (`test-smells.md`): the tested path no longer equals the shipped path, and the hook can fail in production. Use only when no structural seam is possible, isolate the hook tightly, and treat its removal (by refactoring to a real seam) as outstanding debt.

```
// AVOID unless nothing else works — and plan to delete it
def charge(amount):
  if TEST_MODE: return FakeGatewayResult.ok()   // test logic in production
  return realGateway.charge(amount)
```

Prefer, in order: Dependency Injection → Dependency Lookup → Test-Specific Subclass (override the seam method in a test subclass; see `test-doubles.md`) → Humble Object. A Test Hook is an admission that the design resisted all of them.

---

## Anti-Patterns Table

| Anti-Pattern | Why It's Wrong | Correct Alternative |
| --- | --- | --- |
| `InternalsVisibleTo` + `internal set` for tests | Weakens encapsulation for test convenience | Add a public constructor that accepts values |
| Reflection into private members as primary strategy — Java: `getDeclaredMethod`/`getDeclaredField` + `setAccessible(true)`, `Method.invoke` on a private/protected member; C#: `Type.GetMethod(..., BindingFlags.NonPublic \| BindingFlags.Instance)`, `Type.InvokeMember`; Python: `getattr`/`setattr`/`hasattr` on a name-mangled (`_ClassName__attr`) or underscore-prefixed attribute; JS/TS: bracket-notation into a `private`/non-exported member, or `Object.getOwnPropertyDescriptor`/`Object.defineProperty` to reach one | Fragile; breaks on rename; masks coupling — this is an architecture/encapsulation issue the test is reaching around, not a test-hygiene nit | Pick by shape of the code: extract the logic into a collaborator with its own public seam; relax visibility to package-private/internal only when a production collaborator in the same module/assembly independently needs it — never as a grant solely so the test can reach in (that recreates the `InternalsVisibleTo`/`@VisibleForTesting` rows above); or test the behavior through the existing public API (if already reachable) |
| Static test helper that mutates private state | Bypasses object invariants | Use Test Data Builder with public construction |
| Mocking concrete classes | Fragile; requires virtual/open methods; masks design issues | Extract interface; mock the interface |
| Tests configuring global/static state | Shared state causes order-dependent failures | Inject dependencies through constructors |
| Changing `private set` to `public set` for test access | Removes invariant protection | Add constructor parameter instead |
| `[InternalsVisibleTo]` / `@VisibleForTesting` as the primary testability mechanism | Couples test and production assemblies | Redesign the API surface so tests don't need access to internals |

---

## References

- Michael Feathers, *Working Effectively with Legacy Code* — seam insertion, Parameterize Constructor, Extract Interface
- Mark Seemann & Steven van Deursen, *Dependency Injection: Principles, Practices, and Patterns* — Pure DI, Composition Root
- Steve Freeman & Nat Pryce, *Growing Object-Oriented Software, Guided by Tests* — outside-in TDD, mock-roles-not-objects
- Vladimir Khorikov, *Unit Testing: Principles, Practices, and Patterns* — resilient vs. fragile tests
