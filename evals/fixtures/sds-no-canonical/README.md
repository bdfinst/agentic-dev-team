# Fixture: sds-no-canonical

**Skill**: semantic-duplication-scan  
**Scenario**: All copies of a duplicated concept are infrastructure-coupled — no clear canonical

## Setup

Three source files, each computing "order total", each importing infrastructure-specific dependencies:

1. `src/api/order-handler.ts` — imports Express `Request`/`Response` → infrastructure
2. `src/db/order-repo.ts` — imports `pg` Pool → infrastructure  
3. `src/queue/order-processor.ts` — imports RabbitMQ client → infrastructure

All three compute the same sum of (quantity × unit price) for line items.

## Expected Behavior

- One duplicate cluster reported with all three file:line references
- Output: `canonical: none — a new domain-layer implementation may be required`
- All three entries listed with their `file:line` references
