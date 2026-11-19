# Entangled Workflows

Reference file for `system-test-design`, `cd-test-architecture`, and `test-design-advisor`.

An entangled workflow spans several deployables through a dependency that no explicit interface describes, so a contract test cannot detect a break. MinimumCD lists entangled domain workflows that span multiple deployables as a valid use of E2E tests (<https://beyond.minimumcd.org/docs/foundations/testing-fundamentals/test-types/>, end-to-end section).

Each entangled workflow found is both an E2E candidate and a design finding. Cite each sign with a file path. Label each sign `observed` (read in code or config) or `inferred` (deduced from names or structure).

Three kinds follow. Each has **Signs**, **What the guarding E2E asserts**, and **Decoupling step**.

## Shared table or schema

Two or more deployables read or write the same table, view, stored procedure, or schema.

**Signs:**

- Two repos reference the same table name in queries, ORM mappings (for example EF `DbSet` or `ToTable`), or stored-procedure calls.
- Connection strings point at the same database and schema.
- One repo owns the migrations while another maps the same tables without them.
- A deployable reads a table that another deployable writes, instead of using an API or a message.

**What the guarding E2E asserts:** data written by one deployable is read correctly by the other. It does not assert either deployable's business logic.

**Decoupling step:** one deployable owns the table and exposes the data through an API or event. A contract test covers the boundary. An integration test covers the owner's data access.

## Entangled value object

Deployables share a domain type through a library, package, vendored module, or copied source, so a type change changes the behavior of each deployable.

**Signs:**

- A shared package holds domain types, not only DTOs. Names such as `domain`, `common`, `core`, `shared`, and `model` are hints; read the contents before deciding.
- The types hold behavior: validation, calculations, state transitions, or rules.
- Two deployables serialize the same domain type directly instead of mapping a DTO at the boundary.
- Copies of the type are kept in step by hand.
- Deployables run different versions of the library.

**What the guarding E2E asserts:** a value created in one deployable keeps its meaning in the other (for example, an amount keeps its currency and rounding). It does not assert the type's internal logic, which the shared library's unit tests own.

**Decoupling step:** keep only DTOs in the shared package. Map to each deployable's own domain types at the boundary. A contract test covers the DTO.

Value-object examples:

- **Money**: currency, rounding, decimal places, cross-currency comparison.
- **Identifier**: format, prefix, checksum.
- **Status**: enumeration values or their order. An added value breaks the other reader.
- **Date/time**: time zone, inclusive end, precision, business date.
- **Measured quantity**: unit. A changed unit is off by a conversion factor.

## Lockstep deployment

Two or more deployables must deploy together, or in a fixed order, to work.

**Signs:**

- One pipeline, release, or stage deploys several deployables together, with docs or comments saying they must go together.
- A shared version number, or an exact pin of another deployable.
- A change that needs a matching change in another repo in the same release (for example a renamed field with no compatibility period).
- A migration that breaks another deployable's deployed version.
- Runbooks that describe a deploy order.

**What the guarding E2E asserts:** the workflow that crosses them, run at the versions to be deployed together. If partial deploys must work, it also asserts the new version of one deployable with the deployed version of the other.

**Decoupling step:** make each change backward compatible (expand, migrate, contract). Add contract tests with provider verification. Add a pipeline gate that blocks a deploy that breaks a contract.

## Related

- `test-layer-ownership.md`: a shared table, shared domain type, or lockstep deployment is not an explicit interface, so ownership question 4 (contract) does not apply to it.
- `cd-test-architecture.md`: *Entangled workflow candidate* criteria and E2E placement.
