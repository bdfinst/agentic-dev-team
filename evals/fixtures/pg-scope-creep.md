# Plan: fix-invoice-rounding

**Files:** `src/invoice.ts`, `tests/invoice.test.ts`

## Steps

- [x] Step 1 — Add a failing test for half-cent rounding (RED).
- [x] Step 2 — Fix `roundLineItem()` to round half-up (GREEN).
- [ ] Step 3 — Update the changelog.

## Git log (most recent first)

```
9f8e7d6  Step 2: round line items half-up; add telemetry counter and refactor pricing
c3b2a10  Step 1: add failing half-cent rounding test (tests/invoice.test.ts)
```

## Files changed by commit 9f8e7d6

```
M src/invoice.ts          # in scope
A src/telemetry.ts        # NOT in the plan's declared Files
M src/pricing.ts          # NOT in the plan's declared Files
```

## Notes

The plan's declared scope is `src/invoice.ts` and `tests/invoice.test.ts`. Commit
9f8e7d6 also adds `src/telemetry.ts` and rewrites `src/pricing.ts` — a new
telemetry counter and a pricing refactor that no plan step calls for. This is
scope creep: changed files that map to no plan step, plus functionality beyond
the stated rounding fix.
