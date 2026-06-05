# Result Verification

Reference file for `test-review`, `test-smell-review`, and the `test-design-advisor` skill. This file covers the **Verify** phase — how a test asserts the outcome — and the patterns that make a failure point straight at its cause. Where `test-doubles.md` chooses the collaborator stand-in, this file chooses the *assertion*.

Source: Gerard Meszaros, *xUnit Test Patterns* (xunitpatterns.com) — Result Verification chapter. Language- and framework-agnostic — described by role, not any assertion library's API.

Core principle: **verify one logical condition per test, and make every assertion say what it expected and why** — so a red test localizes the defect instead of hiding it.

---

## Verification style: state vs behavior

| Style | What it checks | Use when |
|---|---|---|
| **State verification** | The SUT's resulting state / return value after exercise | **Default.** The outcome is observable as a value or state |
| **Behavior verification** | That the SUT *called* a collaborator a certain way | Only at a true side-effect boundary with no observable state (e.g. a message was published) |

Prefer state verification; reach for behavior verification only when there is no state to assert. The *double* that enables behavior verification (spy/mock) is chosen in `test-doubles.md`; here, decide *whether* behavior verification is even the right approach.

---

## Assertion patterns

| Pattern | What it is | Use when | Fixes |
|---|---|---|---|
| **Assertion Method** | A single primitive assert on one value, with a message | A single expected value | baseline |
| **Expected Object** | Build the whole expected object and assert equality in **one** comparison | Asserting many fields of one result | **Assertion Roulette**, field-by-field clutter |
| **Custom Assertion** | A domain-named assertion encapsulating a comparison **and** an intent-revealing failure message (`assertIsOverdue(account)`) | The same non-trivial comparison recurs, or the default failure message is opaque | duplication + poor diagnostics |
| **Verification Method** | A named sequence of assertions reused across tests | A multi-assertion check repeats with the same meaning | Test Code Duplication in the Verify phase |
| **Guard Assertion** | Assert a precondition **before** the main assertion, so a missing precondition fails clearly | The main assertion would otherwise throw a cryptic null/empty error | misleading failures |
| **Delta Assertion** | Assert the *change* relative to a captured baseline, not an absolute value | Working against a Shared/persistent fixture whose absolute state you don't control | brittle absolute assertions on shared fixtures |

---

## Rules

- **One logical condition per test.** Several unrelated assertions in one method is an Eager Test — split it (`test-organization.md` / `test-refactoring.md`).
- **Locatable intent.** Every assertion carries a message or is self-describing, so a failure names the expectation.
- **No magic values.** Don't assert against unexplained literals; name the expected value or derive it visibly (avoid hard-coded values whose meaning is lost).

**Decision flow:** single value → Assertion Method with a message → multi-field object → **Expected Object** → repeated/complex domain comparison → **Custom Assertion** / **Verification Method** → precondition that would fail cryptically → **Guard Assertion** → outcome relative to a shared fixture → **Delta Assertion**.

---

## How this connects to the rest of the toolkit

- **`test-smells.md`** — the smells these fix: Assertion Roulette, Obscure Test, Fragile/Overspecified Test, Hard-Coded Values.
- **`test-doubles.md`** — behavior verification with mocks/spies; choose the double there, decide the verification approach here.
- **`test-strategy.md`** — Delta Assertion is the verification counterpart of a Shared/persistent Fixture.
- **`test-organization.md`** — Verify is the third of the Four-Phase Test.
- **`test-refactoring.md`** — the moves that get an existing test here: Introduce Expected Object, Extract Custom Assertion / Verification Method, Add Guard Assertion, Split Test.
