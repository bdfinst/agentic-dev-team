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

## Anti-Patterns Table

| Anti-Pattern | Why It's Wrong | Correct Alternative |
|---|---|---|
| `InternalsVisibleTo` + `internal set` for tests | Weakens encapsulation for test convenience | Add a public constructor that accepts values |
| Reflection into private members as primary strategy | Fragile; breaks on rename; masks coupling | Extract to public API or create a proper test entry point |
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
