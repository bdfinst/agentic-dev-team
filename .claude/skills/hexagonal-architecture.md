# Hexagonal Architecture (Ports & Adapters)

## Overview
Design systems with clear separation between business logic and infrastructure. The domain core has zero dependencies on outer layers; all external interactions flow through explicitly defined ports and adapters.

## Core Concepts

### Ports
- Interfaces that express application intent independent of technology
- **Inbound ports** (driving): define use cases the application exposes (e.g., `CreateOrderUseCase`)
- **Outbound ports** (driven): define what the application needs from the outside world (e.g., `OrderRepository`, `PaymentGateway`)

### Adapters
- Concrete implementations that connect ports to external systems
- **Inbound adapters**: REST controllers, CLI handlers, message consumers, GraphQL resolvers
- **Outbound adapters**: database repositories, HTTP clients, message publishers, file storage

### Dependency Rule
- All dependencies point inward toward the domain core
- Domain knows nothing about adapters, frameworks, or infrastructure
- Adapters depend on ports, never the reverse

## Project Structure

```
src/
├── domain/              # Pure business logic, no framework dependencies
│   ├── model/           # Entities, value objects, aggregates
│   ├── service/         # Domain services
│   └── event/           # Domain events
├── application/         # Use cases / application services
│   ├── port/
│   │   ├── inbound/     # Use case interfaces (driving ports)
│   │   └── outbound/    # Repository/gateway interfaces (driven ports)
│   └── service/         # Use case implementations
├── infrastructure/      # Framework and technology concerns
│   ├── config/          # Dependency injection, app configuration
│   └── persistence/     # Database migrations, ORM config
└── adapter/
    ├── inbound/         # Controllers, CLI, event consumers
    └── outbound/        # Repository impls, API clients, message publishers
```

## Guidelines
- Every external dependency gets its own adapter behind a port
- Test domain logic by substituting adapters (e.g., in-memory repository for unit tests)
- Introduce a new port when a new category of external interaction appears
- Reuse existing ports when the interaction pattern is the same
- Keep the application layer thin: orchestrate domain objects, don't duplicate domain logic
