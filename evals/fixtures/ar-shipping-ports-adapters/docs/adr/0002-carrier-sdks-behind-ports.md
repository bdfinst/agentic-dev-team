# 2. Carrier SDKs stay behind domain ports

Status: Accepted

## Decision

The domain defines a `CarrierGateway` port. Each carrier SDK is imported only
by its adapter in `src/infrastructure/carriers/`. `src/main.ts` selects and
constructs the adapters.
