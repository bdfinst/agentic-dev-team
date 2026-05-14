# Fixture: sds-subdirectory-scope

**Skill**: semantic-duplication-scan  
**Scenario**: Scoped scan only re-annotates files inside the given path

## Setup

Register has entries for:
- `src/pricing/discount.ts` (inside scope)
- `src/checkout/cart.ts` (outside scope)

Command: `/semantic-scan src/pricing`

## Expected Behavior

- Only `src/pricing/discount.ts` is re-annotated
- Entry for `src/checkout/cart.ts` is unchanged in the register
- `lastScanCommit` updated to HEAD
- Exit code: 0
