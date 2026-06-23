# Value Patterns (Test Data Sourcing)

Reference file for the `test-design-advisor` skill and the `test-review` / `test-smell-review` agents. Where `fixture-construction.md` decides *how the fixture object is built* and `test-doubles.md` decides *what stands in for a collaborator*, this file decides the **scalar values** that go into them: the literals, computed values, and generated values a test feeds the SUT and asserts against. Choosing the wrong value source is a common, quiet cause of Obscure Test, Fragile Test, and Erratic Test.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Ch. 27 *Value Patterns*. Language- and framework-agnostic.

Core principle: **every value in a test should reveal its intent.** A reader should see *why* a value is what it is — whether it's significant, derived from another value, or simply "some unique thing that doesn't matter." A magic literal whose meaning is lost is the Hard-Coded Values smell.

---

## The four value sources

| Pattern | What it is | Use when | Risk if misused |
|---------|-----------|----------|-----------------|
| **Literal Value** | A constant written directly in the test (`42`, `"ACTIVE"`) | The exact value *is* the point — a boundary, a known-pathological case, a spec example | Unexplained → Hard-Coded Values smell; reused across tests → fragile coupling |
| **Derived Value** | Computed in the test from other values via a visible expression | A value relates to another by a rule (`total = price * (1 + TAX_RATE)`); the relationship documents the requirement | Same math bug can hide in both test and SUT — pin a few cases with Literals |
| **Generated Value** | Produced at run time (sequence, UUID, faker) | The value must be **unique** (DB keys, idempotency tokens) or genuinely **doesn't affect** the outcome | Random generation → Erratic/Nondeterministic Test; only generate when uniqueness is required |
| **Dummy Object** | A do-nothing placeholder passed only to satisfy a signature | An argument is required by a method but **never used** on the path under test | If the SUT actually touches it, you need a Stub/Fake instead |

---

## Choosing a value source (decision flow)

```
Does the SUT's behavior depend on this specific value?
├─ YES → is it computed from another value by a documented rule?
│        ├─ YES → Derived Value (show the expression; name the constant, e.g. MAX_RETRIES)
│        └─ NO  → Literal Value (name it for its meaning; it's a boundary or spec example)
│
└─ NO → is the value required to be unique (DB key, token, filename)?
         ├─ YES → Generated Value — prefer a *Distinct* (sequence) generator over random
         └─ NO  → is it an object only present to fill a parameter slot?
                  ├─ YES → Dummy Object
                  └─ NO  → a named Literal with an Intent-Revealing Name ("irrelevant" made explicit)
```

---

## Notes that matter when evaluating tests

- **Derived vs. Literal trade-off.** Derived Values make a requirement's *relationship* explicit and survive legitimate change (raise the tax rate, the test follows). But a shared arithmetic error can appear in both the test and the SUT — so cover a few pathological cases with hand-computed **Literal** Values as a cross-check.
- **Distinct over Random.** A *Distinct Generated Value* (an incrementing sequence, reset per run) gives uniqueness **and** repeatability — the same values appear each run, so failures reproduce. A *Random Generated Value* trades reproducibility for coverage and usually creates an Erratic Test; if you must use one, log the seed/value on failure so the case can be replayed. Default to Distinct.
- **Generate only for uniqueness.** Don't reach for a generator just to avoid choosing a number. Unnecessary generation introduces nondeterminism (different values can expose different bugs — single- vs. multi-digit formatting, etc.). Prefer a named Literal when the value doesn't need to be unique.
- **Dummy ≠ Stub.** A Dummy is *never used*; if any method on it is called, the test should blow up (that's the signal you actually needed a Stub or Fake). Using a Dummy keeps Obscure Test away by stating "this argument is irrelevant" instead of constructing a real, distracting object. (Choosing between Dummy/Stub/Fake/Mock lives in `test-doubles.md`.)
- **Anonymous vs. significant.** Make the *significant* values prominent and push *irrelevant* ones behind builder defaults or a clearly-named "anonymous" helper, so the cause-and-effect the test proves isn't buried in noise (`fixture-construction.md`).

---

## How this connects to the rest of the toolkit

- **`test-smells.md`** — Hard-Coded Values, Irrelevant Information, Erratic Test (from random values) are the smells these patterns prevent or, misused, cause.
- **`fixture-construction.md`** — Test Data Builders carry sensible defaults so only the *significant* values surface in a test; value patterns choose those values.
- **`test-doubles.md`** — Dummy Object sits at the boundary between value patterns and doubles; the Stub/Fake/Mock decision is there.
- **`result-verification.md`** — Derived Values are the basis of a *Derived Expectation*; Generated Values often pair with a *Delta Assertion* against a shared fixture.
- **`test-automation-principles.md`** — *Communicate Intent* (no unexplained literals) and *Repeatable Test* (Distinct over Random) are the principles at stake.
