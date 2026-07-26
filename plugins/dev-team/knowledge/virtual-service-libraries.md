# Virtual-Service Libraries — Record-and-Replay Catalog

Reference file for the `cd-test-architecture` skill's Downstream-service
branch (`Build (Fake)` bullet — see `skills/cd-test-architecture/SKILL.md`).
Catalogs the record-and-replay virtual-service library preferred for each
profiled backend stack, with a hand-rolled Fake as backup. These are
recommended starting points, not mandates: drop items that don't apply,
add what a component clearly needs.

## Preferred vs. backup

A record-and-replay virtual-service library is the **preferred** pre-merge
double for outbound HTTP; a hand-rolled Fake is the **backup** — used when
the operator declines the library, or when no protocol-appropriate library
exists for the component's adapter kind. See `skills/cd-test-architecture/SKILL.md`'s
Downstream-service branch (`Build (Fake)` bullet) for the full
accept/name-a-different-library/decline interaction — not restated here.

## Catalog

| Stack | Library | Protocol scope |
|---|---|---|
| `dotnet` | WireMock.Net | HTTP |
| `node` | Nock | HTTP |
| `spring-boot` | WireMock | HTTP |
| `go` | A Go-native record-and-replay library (e.g. `go-vcr`) | HTTP |
| `django` | VCR.py (`vcrpy`) | HTTP |

All five catalog entries above are HTTP-focused. Message-broker
virtualization for Event Consumer/Producer components has no equally
mature per-stack tool — Mountebank is the closest general-purpose
fallback, and it is itself thinner coverage than the HTTP-focused tools
above, not an equivalent substitute.

## Resolution order

Three-valued precedence for selecting the tool a `Build (Fake)` row
recommends:

1. **Existing tool detected** — the target repo already depends on (or
   already uses in its tests) a virtual-service/record-replay library.
   That tool becomes the default; no switch is suggested.
2. **Catalog default** — when no existing tool is detected, the stack's
   entry from the table above.
3. **Operator override or decline** — the operator names a different
   library (used instead of 1 or 2), or declines (hand-rolled Fake, the
   backup).
