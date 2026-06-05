# Property-based testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior has an **invariant that holds for all inputs** — a roundtrip (`decode(encode(x)) == x`), a mathematical law (commutativity, idempotency, sum-preservation), an ordering/closure property — rather than a handful of known example pairs.

**What it is.** Instead of fixed examples, declare a property and a generator; the framework generates hundreds of random inputs, and on failure **shrinks** to the minimal counterexample.

**When to use.** Parsers/serializers, encoders, money/quantity math, sorting/merging, state machines, anything with an algebraic law. Pairs well with a few example tests for documentation.

**Trade-offs / cost.** Finding the right property is the hard part — a weak property passes vacuously. Generators for complex domain types take effort. Slower than example tests; seed failures so they reproduce.

**Minimal shape.** `forAll(integers, integers, (a,b) => add(a,b) === add(b,a))`.

**Complements.** A unit/integration *technique*, not a layer — apply it at the layer where the invariant lives. Tools: fast-check (JS), Hypothesis (Python), jqwik (Java), FsCheck (.NET). For *malformed/hostile* inputs rather than law-checking, see `fuzz.md`.
