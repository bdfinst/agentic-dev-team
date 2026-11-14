# Shipping service architecture

Hexagonal (ports and adapters). Dependencies point inward.

| Layer | Directory | May depend on |
| --- | --- | --- |
| Domain | `src/domain/` | nothing outside `src/domain/` |
| Application | `src/application/` | domain |
| Infrastructure | `src/infrastructure/` | domain, application, third-party SDKs |
| Composition root | `src/main.ts` | every layer; it only constructs and wires objects |

Ports are interfaces owned by the domain (`src/domain/ports/`). Each external
system gets one adapter under `src/infrastructure/` that implements a port and
wraps the vendor SDK. See ADR 2.
