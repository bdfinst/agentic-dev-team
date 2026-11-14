# Checkout service architecture

Layers, with dependencies pointing inward:

| Layer | Directory | May depend on |
| --- | --- | --- |
| Domain | `src/domain/` | nothing outside `src/domain/` |
| Application | `src/application/` | domain, application ports |
| Infrastructure | `src/infrastructure/` | domain, application ports, third-party clients |

Application use cases reach the outside world only through the port
interfaces in `src/application/ports/`. Infrastructure adapters implement
those ports and are wired in `src/main.ts`.
