# Fixture: sds-prefilter-trivial

**Skill**: semantic-duplication-scan  
**Scenario**: Pre-filter correctly excludes trivial functions

## Purpose

Verifies that the skill's pre-filter step excludes all trivial functions from the computation register, producing no register entries for a file containing only trivial code.

## Expected Behavior

When `/semantic-scan` is run against a project containing only `trivial-functions.ts`:

- No `computation-register.json` is created
- Output: `"No computation units found to analyze"`
- Exit code: 0

## Why Each Function Is Trivial

| Function | Reason excluded |
|----------|----------------|
| `getUserName` | Getter — reads and returns a field, no computation |
| `logUser` | Pass-through delegator — no transformation |
| `identity` | Identity function — returns input unchanged |
| `OrderItem` constructor | Only assigns parameters to fields |
| `Pricing.basePrice` getter | Single-expression property accessor |
