# Fixture: sds-no-duplicates

**Skill**: semantic-duplication-scan  
**Scenario**: Clustering finds no duplicates when all concepts are semantically distinct

## Register State (pre-populated for clustering test)

Five entries with distinct canonicalized domainConcepts:

1. `applyDiscount` — domain — "discounted price"
2. `calculateTax` — domain — "tax amount"  
3. `validateCouponCode` — application — "coupon validity"
4. `computeShippingWeight` — domain — "shipping weight"
5. `formatReceiptLine` — presentation — "receipt line text"

## Expected Behavior

After clustering:
- No duplicate clusters reported
- Output: `No semantic duplication detected`
- Exit code: 0
