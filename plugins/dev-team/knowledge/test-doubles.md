# Test Doubles

Reference file for `test-smell-review`, `test-review`, and the `test-design-advisor` skill. A test double is any object that stands in for a real collaborator in a test. Choosing the wrong kind of double is the most common cause of fragile, over-specified tests.

Source taxonomy: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com). Language-agnostic — described by role, not by any mocking library's API.

Core principle: **prefer the simplest double that lets the test verify the behavior.** Reach for a Mock only when the interaction *is* the behavior under test. Over-mocking couples tests to implementation and produces the Overspecified Software smell (see `test-smells.md`).

---

## The Five Doubles

| Double | What it does | Verification style | Use when |
|--------|-------------|-------------------|----------|
| **Dummy** | Passed but never used; fills a required parameter | none | A constructor/method signature demands an argument the test path never touches |
| **Stub** | Returns canned answers to calls made during the test | **state** (assert on the SUT's output/state) | The SUT *reads* from a collaborator and you need to control what it reads (config, query result, clock) |
| **Spy** | A stub that also records how it was called, for later inspection | **behavior** (assert after the act) | You need to confirm an outgoing call happened, but want to assert *after* the action, not pre-program expectations |
| **Mock** | Pre-programmed with expectations; fails the test if calls don't match | **behavior** (expectations verified) | The interaction itself is the observable behavior (e.g., "an email *is sent*") and there's no state to assert on |
| **Fake** | A working but lightweight implementation (in-memory DB, in-memory queue) | **state** | A stub/mock would need so much call-by-call setup that a real-ish implementation is simpler and more faithful |

A **Test Spy** and a **Mock** both do behavior verification; the difference is *when* and *how* you specify expectations. Spy = act, then assert on recorded calls. Mock = set expectations up front, library verifies them. Spies usually read better and fail less cryptically.

---

## State Verification vs. Behavior Verification

| | State verification | Behavior verification |
|---|---|---|
| **Asserts on** | The SUT's return value or resulting state | The calls the SUT made to collaborators |
| **Doubles used** | Stub, Fake | Mock, Spy |
| **Coupling** | Low — survives refactors that preserve outcome | High — breaks when the *how* changes, even if outcome is identical |
| **Default?** | **Yes — prefer this** | Only when there's no observable state to assert |

Rule of thumb: if you *can* assert on a result or a state change, do that and use a Stub/Fake. Use a Mock/Spy only for genuine side-effect-only boundaries — sending a message, writing to a log/queue, calling a payment gateway — where the call is the whole point.

---

## Choosing a Double (decision flow)

```
Does the SUT READ from the collaborator (needs a controlled answer)?
├─ YES → can you then assert on the SUT's output or state?
│        ├─ YES → Stub (state verification). Done.
│        └─ NO, the read drives a side effect you must confirm → Spy
│
Does the SUT only WRITE to the collaborator (side-effect-only boundary)?
├─ YES → is the call itself the behavior under test (email sent, event published)?
│        ├─ YES → Mock or Spy (behavior verification)
│        └─ NO, it's incidental → Dummy or a no-op Stub; don't assert on it
│
Is per-call stub/mock setup so heavy it obscures the test?
└─ YES → Fake (in-memory implementation), assert on its resulting state
```

---

## How the double is built: Configurable vs. Hard-Coded

The five doubles above are *roles*; this is the orthogonal question of *how the double gets its canned answers*. Both forms are legitimate — the choice is about reuse vs. transparency.

| Form | What it is | Use when | Watch for |
|------|-----------|----------|-----------|
| **Configurable Test Double** | A reusable double the test programs at run time with the values to return / calls to expect (what Mockito/JMock/NSubstitute/Sinon generate) | The same collaborator is doubled across many tests with different canned values; you want one mechanism, configured per test | Configuration becomes so verbose it obscures the test — a sign to extract a builder or downgrade a Mock to a Stub |
| **Hard-Coded Test Double** | A purpose-built class (or *Inner Test Double* — a nested/anonymous class, or a Test-Specific Subclass) with the canned values **baked into its code** | The behavior is specific to one or a few tests; a framework can't express it; or you want a named, self-documenting stand-in | Proliferation of one-off double classes; if it recurs with varying data, switch to a Configurable form |

Neither is "better." Reach for a **Configurable** double when one collaborator is stubbed many ways across the suite; reach for a **Hard-Coded** double when a specific, named behavior reads more clearly than per-test configuration (or the framework can't produce it).

---

## Test-Specific Subclass

When you can't substitute a collaborator from outside — the dependency is created internally, or the thing you need to control is a *method of the SUT itself* — subclass the real class **in the test** and override just the seam method to inject an indirect input or null out an unwanted side effect.

```
// Override only the narrow seam; inherit everything else real
class TestableOrderService extends OrderService:
  override fetchRate(): return 1.25   // control one indirect input
```

Use it to: gain control of an indirect input without a full injection refactor; expose a protected hook for the test; or stand up a Hard-Coded double by subclassing a real collaborator. **Constraints** (from *Don't Modify the SUT*, `test-automation-principles.md`): override **only** what the test must control — never a method whose behavior this test is verifying, or you're testing the override, not the code. Treat it as a bridge toward a real seam (`testability-patterns.md`), not a permanent design.

---

## Common Misuses (flag these)

| Misuse | Why it's wrong | Fix |
|--------|---------------|-----|
| Mocking a value object or pure function | Nothing to verify; adds coupling for zero benefit | Use the real object |
| Mocking the type under test | You're testing the mock, not the code | Use the real SUT; double only its *collaborators* |
| Asserting exact call order/count when order doesn't matter | Overspecified Software smell; fragile | State verification, or assert only the call that matters |
| Stub returns drive an `if` that's never asserted | Dead control; the test proves nothing about that branch | Assert the branch's effect, or remove the setup |
| A Mock where a Stub would do (no side-effect being verified) | Tests implementation detail instead of outcome | Downgrade to Stub + state assertion |
| Mocking a concrete class instead of an interface/port | Couples to the implementation type; see `testability-patterns.md` | Extract an interface/port; double that |
| Mocking a collaborator internal to / owned by the same component or bounded context as the SUT | This is a boundary-selection error, distinct from the injection-mechanism problem above — the collaborator isn't a true external-boundary system (third-party API, another team's service, infra the team doesn't control), it's part of what should be under test | Assemble the real component and exercise the collaborator as real (sociable unit/component test); double only genuine external-boundary systems — see `component-test-patterns.md`'s core principle |

---

## Relationship to testability

If a collaborator can't be substituted at all (new-ed up internally, static singleton, hidden global), that's a **production-code** problem, not a test problem — introduce a seam per `testability-patterns.md` (constructor injection, interface extraction) before choosing a double. The double taxonomy assumes the collaborator is already injectable.

## Boundaries

- Don't flag a Fake (in-memory repo/DB) as "not testing the real thing" — at unit/integration level a Fake is a legitimate, often *better*, choice than a heavily-stubbed real dependency. Real-dependency fidelity is the job of contract and integration tests (see `test-pyramid.md`, `microservice-testing.md`).
- A single Mock at a true side-effect boundary is correct, not a smell. The smell is *pervasive* mocking that pins down internal call sequences.
