# Unit of work: slice 2 — loyalty discount

Complexity: standard

Stage 1 spec-compliance review: pass.

Changed files (see `diff.patch`):
- `src/pricing/discount.ts` — new loyalty-tier discount rule (business logic)
- `tests/discount.test.ts` — tests for the rule

`src/pricing/discount.ts` is an internal module of the pricing package: no production code outside `src/pricing/` imports it (only its own test does), and this change adds no new public API.
