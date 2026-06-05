# Schema-validation testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior produces or consumes a payload governed by a **declared schema** — an OpenAPI/Swagger spec, JSON Schema, Avro/Protobuf, a GraphQL type. The risk is the payload **drifting from its own declared shape**.

**What it is.** Assert that real request/response payloads validate against the schema artifact — and, in reverse, that the schema matches what the code emits. The schema becomes an executable spec, not just documentation.

**When to use.** Public/partner APIs with a published spec, event payloads on a shared bus, config files with a schema, codegen boundaries. Catches "docs say one thing, code does another" before consumers do.

**Trade-offs / cost.** Validates *shape*, not *meaning* — a semantically wrong-but-well-formed payload still passes (cover that with unit/contract tests). The schema must be kept authoritative or the check rots.

**Minimal shape.** `expect(validate(openapi.paths['/orders'].post.response, actualBody)).toPass()`.

**Complements.** Integration/component on the boundary. **Not a substitute for contract testing** between two owned services — for consumer↔provider agreement route to `microservice-testing.md` (CDC). Schema-validation checks conformance to a *declared* schema; CDC checks two parties still *agree*. Cross-reference `security-review` for input-validation at trust boundaries. Tools: ajv, openapi-validator, Spectral, schemathesis.
