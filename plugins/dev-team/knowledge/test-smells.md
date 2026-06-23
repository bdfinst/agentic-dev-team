# Test Smells

Reference file for `test-smell-review` and `test-review` agents. A test smell is a symptom in test code that signals a design problem in the test or in the code under test. Each smell below gives a **detection signal** (what to grep/read for), **why it hurts**, and the **fix** — which is sometimes a test change and sometimes a production-code change.

Source taxonomy: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com). Language-agnostic — signals are described by behavior, not syntax.

Core principle: a test smell is never fixed by suppressing the test. If a test is hard to write, hard to read, or flaky, the test is reporting a real design problem. Fix the cause.

---

## Smell Categories

xUnit Test Patterns groups smells into three levels. Detect at all three:

- **Code smells** — visible in a single test method (readability, assertions).
- **Behavior smells** — visible only when tests run (flakiness, fragility, slowness).
- **Project smells** — visible across the suite over time (manual intervention, production bugs slipping through).

---

## Code Smells (single test, readable now)

| Smell | Detection signal | Why it hurts | Fix |
|-------|-----------------|--------------|-----|
| **Obscure Test** | Reader cannot tell what behavior is verified without running it; setup buried in `beforeEach`, helpers, or shared fixtures far from the assertion | Test stops being executable documentation; maintenance becomes guesswork | Inline the relevant setup; name intent; one clear arrange-act-assert. Sub-types below. |
| → Eager Test | One test method exercises many behaviors / many asserts on unrelated outcomes | A failure doesn't pinpoint which behavior broke | Split into one behavior per test |
| → Mystery Guest | Test depends on external data it doesn't create (a file on disk, a seeded DB row, a fixture in another module) | Reader can't see the inputs; data drift breaks the test silently | Create the data in-test (Fresh Fixture) or via a Test Data Builder |
| → General Fixture | A shared setup builds far more than this test needs | Reader can't tell which parts matter; coupling across tests | Build only what each test uses (Minimal Fixture) |
| → Irrelevant Information | Setup exposes values that don't affect the assertion | Noise hides the cause-effect the test proves | Hide irrelevants behind builders with sensible defaults |
| **Assertion Roulette** | Multiple bare assertions with no messages; on failure you can't tell which line failed | Failure triage requires a debugger | Give assertions descriptive messages, or split tests; use single-behavior assertions |
| **Conditional Test Logic** | `if`/`switch`/loops/try-catch around assertions; test takes different paths | Some assertions may never run; the test verifies different things on different runs | Remove branching; use parameterized tests or separate cases; assert unconditionally |
| **Hard-Coded / Magic Values** | Unexplained literals in assertions (`expect(x).toBe(42)`) | Reader can't tell why 42 is correct; fragile to legitimate change | Name the constant for its meaning, or derive it visibly from inputs |
| **Test Code Duplication** | Copy-pasted arrange or assert blocks across tests | A behavior change forces edits in N places; drift | Extract Creation/Custom Assertion methods or a Test Data Builder |
| **Test Logic in Production** | Production code contains `if (testMode)`, test-only hooks, or back doors | Tested code path ≠ shipped code path; false confidence | Remove; achieve control via dependency injection / seams (see `testability-patterns.md`) |

---

## Behavior Smells (only visible when tests run)

| Smell | Detection signal | Why it hurts | Fix |
|-------|-----------------|--------------|-----|
| **Erratic Test** (flaky) | Passes/fails non-deterministically across runs | Destroys trust in the suite; teams start ignoring red | Eliminate the non-determinism source — see sub-types |
| → Interacting Tests | Test passes alone, fails in suite (or vice versa); order-dependent | Shared mutable state between tests | Fresh Fixture per test; no shared writable state |
| → Test Run War | Intermittent failures only when suite runs concurrently / on CI | Tests share an external resource (same DB, same file, same port) | Isolate resources per test run (unique schema, temp dir, ephemeral port) |
| → Nondeterministic timing | `Date.now()`/`now()`, `Math.random()`/`Random`, `sleep`, real timers in assertions | Clock/RNG/scheduler drift | Inject a clock/RNG; use fake timers; never `sleep` to await |
| → Resource Leakage / Optimism | Test assumes a resource exists or is clean; leaves state behind | Cascading failures, slow degradation | Set up and tear down own resources; assert preconditions |
| **Fragile Test** | A change unrelated to the behavior under test breaks the test | Maintenance tax; discourages refactoring | Test through stable public behavior, not internals — see sub-types |
| → Interface Sensitivity | Renaming/reshaping an API breaks many tests | Tests bound to signatures, not behavior | Centralize creation/interaction in helpers (one place to update) |
| → Behavior Sensitivity | Changing unrelated behavior breaks the test | Over-specified expectations | Assert only what this behavior guarantees |
| → Overspecified Software (mock-heavy) | Test asserts exact internal call sequences via mocks | Tests the implementation, not the outcome | Prefer state verification; mock only true boundaries (see `test-doubles.md`) |
| → Context/Data Sensitivity | Breaks when run in a different timezone, locale, or with different seed data | Hidden environmental coupling | Pin locale/timezone; control all inputs explicitly |
| **Slow Tests** | Unit-level tests taking seconds; real I/O (DB, network, disk) in unit tests | Feedback loop collapses; tests get skipped | Replace boundaries with doubles; push slow checks down the pyramid (see `test-pyramid.md`) |
| **Frequent Debugging** | Most test *failures* need an interactive debugger or print statements to locate the cause; failure messages don't tell you what broke | The suite has lost Defect Localization — a red bar that doesn't point at the defect is barely better than no test | Add the missing fine-grained unit/component tests; improve Assertion Messages; run tests after every small change so you remember what you touched (see `test-automation-principles.md` → Defect Localization) |

---

## Project Smells (visible across the suite over time)

| Smell | Detection signal | Why it hurts | Fix |
|-------|-----------------|--------------|-----|
| **Production Bugs** | Defects reach prod despite a green suite | Tests verify the wrong things, or coverage gaps | Add tests at the level the bug lived (often a missing unit/contract test) |
| **High Test Maintenance Cost** | Every feature change forces large test rewrites | Accumulated Fragile/Obscure smells | Address the underlying code & behavior smells; introduce builders & custom assertions |
| **Manual Intervention** | A human must edit config, seed data, or run a step for tests to pass | Tests aren't repeatable or CI-able | Automate setup; make the suite hermetic |
| **Buggy Tests** | Tests pass when the code is broken (or fail when it's correct) | Negative confidence — worse than no test | Verify the test fails for the right reason (mutation testing surfaces these — see `mutation-testing` skill) |
| **Developers Not Writing Tests** | Code lands without tests; test count flat or falling while code grows; "no time to test" | The safety net never forms; the rest of the suite's value erodes as untested code accumulates | Address the *root cause*, not the symptom: schedule pressure (make testing part of "done"), missing skills (coach/pair), or Hard-to-Test Code (fix testability — `testability-patterns.md`). Often paired with Lost Tests (tests silently disabled) |

---

## Detection Workflow

1. **Read each test method** for code smells — can you state the behavior under test in one sentence from the test alone? If not → Obscure Test.
2. **Scan for behavior-smell signals** — clock/RNG/sleep/real-I/O, shared mutable state, exact-call-sequence mock assertions.
3. **Scan the suite shape** for project smells — heavy `beforeAll` shared state, manual setup steps, fixtures referenced but not created in-test.
4. For each finding, decide: **test fix** (rename, split, add message, build fresh fixture) or **production fix** (introduce a seam — defer to `testability-patterns.md`).

## Boundaries

- A single behavior asserted with several related assertions on one object is **not** Eager Test or Assertion Roulette — that's normal.
- Integration/E2E tests are *expected* to touch real resources; "Slow Tests" applies when that work happens at the **unit** level. Confirm the intended test level before flagging (see `test-pyramid.md`).
- Do not flag duplication between two tests that assert genuinely different boundary conditions — that's coverage, not Test Code Duplication.
