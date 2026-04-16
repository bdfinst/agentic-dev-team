# Testing Anti-Patterns

Patterns that produce tests which pass but don't validate behavior. Load during the RED phase when writing tests.

## 1. Testing Mock Behavior

Asserting that a mock was called with specific arguments instead of testing observable outcomes. Tests pass even when real behavior is broken because you're verifying your test setup, not your code. **Fix**: assert on outputs and side effects, not call patterns.

## 2. Test-Only Production Methods

Adding methods to production code solely for testing (e.g., `_getInternalState()`). Pollutes the public API and creates maintenance burden — callers depend on internals that should be free to change. **Fix**: test through the public interface.

## 3. Mocking Without Understanding

Mocking a dependency without reading its contract. The mock silently diverges from real behavior, so tests pass against a fiction. **Fix**: read the dependency's API docs, use the real thing when feasible, or build a well-understood fake.

## 4. Incomplete Mocks

Mocking only the happy path — no errors, edge cases, or state transitions. Tests pass but production fails on the first unexpected response. **Fix**: mock the full contract including error paths and boundary conditions.

## 5. Unvalidated Test Doubles

Using test doubles (mocks, stubs, fakes) at external boundaries without integration tests that verify the doubles match real behavior. The doubles silently drift from reality — tests pass against a fiction while production breaks. **Fix**: follow the [contract testing pattern](../../knowledge/contract-testing.md) — use test doubles in the main test flow (deterministic, every commit), and run separate integration tests against real dependencies to validate the doubles. When a double drifts, the integration test catches it.
