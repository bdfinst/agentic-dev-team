# Fixture: sds-scoped-cross-scope-notice

**Skill**: semantic-duplication-scan  
**Scenario**: Scoped scan produces a cluster that includes an out-of-scope entry

## Setup

Register has:
- `src/pricing/discount.ts::applyDiscount` (domain, inside scope `src/pricing`)
- `src/checkout/cart.ts::computeDiscountedTotal` (presentation, outside scope)

Both compute the same domain concept. Scan invoked with `/semantic-scan src/pricing`.

## Expected Behavior

- Duplicate cluster is reported containing both entries
- Output includes: `Note: this cluster includes 1 entry outside the scoped path — run without scope argument to see full context`
