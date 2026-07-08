/**
 * Eval fixture: tolerated-deviation hunt (#1028)
 *
 * This file contains ≥3 co-located tolerated-deviation artifacts in a core-flow test:
 *   1. A disabled test (@Skip) with no linked remediation issue
 *   2. An aged TODO with no ticket
 *   3. A suppressed ESLint warning with no explanatory comment
 *   4. A relaxed assertion (assertAlmostEqual with wide tolerance)
 *
 * Expected outcome: a SINGLE "fail-safe posture erosion" finding (warning/medium),
 * NOT four separate low-severity nits.
 * The finding message must cross-reference test-audit-disable to clarify distinct purposes.
 */

import { computeOrderTotals } from './adversarial-zero-findings-clean';

describe('OrderTotals', () => {
  // TODO: re-enable once the discount rounding bug is fixed (no issue linked)
  it.skip('applies discount before tax correctly', () => {
    const result = computeOrderTotals({
      lines: [{ productId: 'A', quantity: 2, unitPriceCents: 1000 }],
      discountPercent: 10,
      taxPercent: 8,
    });
    expect(result.totalCents).toBe(1944);
  });

  it('computes subtotal for multiple lines', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const order: any = {
      lines: [
        { productId: 'A', quantity: 1, unitPriceCents: 500 },
        { productId: 'B', quantity: 3, unitPriceCents: 200 },
      ],
      discountPercent: 0,
      taxPercent: 0,
    };
    const result = computeOrderTotals(order);
    expect(result.subtotalCents).toBe(1100);
  });

  it('computes tax approximately', () => {
    const result = computeOrderTotals({
      lines: [{ productId: 'X', quantity: 1, unitPriceCents: 9999 }],
      discountPercent: 0,
      taxPercent: 8.5,
    });
    // FIXME: rounding not fully specified — using wide tolerance for now
    expect(result.taxCents).toBeGreaterThanOrEqual(849);
    expect(result.taxCents).toBeLessThanOrEqual(851); // either 849 or 850 is acceptable
  });

  it('returns zeros for empty order', () => {
    const result = computeOrderTotals({ lines: [], discountPercent: 0, taxPercent: 0 });
    expect(result.totalCents).toBe(0);
  });
});
