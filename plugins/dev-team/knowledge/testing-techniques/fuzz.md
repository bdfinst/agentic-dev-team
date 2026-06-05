# Fuzz testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior **parses or accepts untrusted/unstructured input** — a file/format parser, protocol decoder, deserializer, public API request body, anything at a trust boundary where malformed input is an attack surface.

**What it is.** Feed large volumes of malformed, random, or mutated input and assert the code **never crashes, hangs, or corrupts state** — it either handles or cleanly rejects. Coverage-guided fuzzers mutate toward new code paths.

**When to use.** Input parsers, decoders, file/upload handling, anything reachable by an attacker. The goal is robustness, not a specific output.

**Trade-offs / cost.** Findings are crashes/hangs, not "wrong answer" — pair with example/property tests for correctness. Needs a sanitizer or crash oracle to be useful; can be slow; corpus and seeds need maintenance.

**Minimal shape.** `fuzz(parseConfig)` runs mutated byte strings; any unhandled exception / OOM / timeout is a failure.

**Complements.** Sits at unit/integration on the parser; security-adjacent — cross-reference `security-review` for the trust-boundary finding. For *valid* inputs obeying a law, use `property-based.md`; for *declared schema* conformance, see `schema-validation.md`. Tools: libFuzzer/AFL, jazzer (Java), Atheris (Python), go-fuzz.
