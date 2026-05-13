# Fixture: sds-semanticscanignore-removes-entries

**Skill**: semantic-duplication-scan  
**Scenario**: .semanticscanignore causes previously-registered entries to be removed

## Setup

Register has entries for:
- `src/legacy/old-pricing.ts::calculatePrice`
- `src/domain/pricing.ts::applyDiscount`

`.semanticscanignore` contains:
```
src/legacy/
```

## Expected Behavior

- `src/legacy/old-pricing.ts` is not re-annotated
- Register entry for `src/legacy/old-pricing.ts::calculatePrice` is **removed**
- Entry for `src/domain/pricing.ts::applyDiscount` is unchanged
- Exit code: 0
