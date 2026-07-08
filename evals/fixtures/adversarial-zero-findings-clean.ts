/**
 * Eval fixture: adversarial-review-protocol zero-findings anomaly (#1027)
 *
 * This is a non-trivial file with real logic that is genuinely clean.
 * A review agent producing zero Confirmed findings on this file must:
 *   1. State the checks performed (completeness, evidence, severity, blind spots,
 *      false-negative re-read, lazy exits, and agent-specific challenges)
 *   2. Cap confidence at Medium (zero findings on non-trivial file = sensitivity signal)
 *
 * Expected output excerpt:
 *   "summary": "... Zero findings after honest pass. Checks performed: <list>. Confidence: Medium ..."
 */

export interface OrderLine {
  productId: string;
  quantity: number;
  unitPriceCents: number;
}

export interface OrderSummary {
  lines: OrderLine[];
  discountPercent: number;
  taxPercent: number;
}

export interface OrderTotals {
  subtotalCents: number;
  discountCents: number;
  taxCents: number;
  totalCents: number;
}

/**
 * Compute order totals from an order summary.
 * Discount is applied before tax. All values rounded to nearest cent.
 */
export function computeOrderTotals(order: OrderSummary): OrderTotals {
  if (order.lines.length === 0) {
    return { subtotalCents: 0, discountCents: 0, taxCents: 0, totalCents: 0 };
  }

  const subtotalCents = order.lines.reduce(
    (sum, line) => sum + line.quantity * line.unitPriceCents,
    0
  );

  const discountCents = Math.round(subtotalCents * (order.discountPercent / 100));
  const afterDiscountCents = subtotalCents - discountCents;
  const taxCents = Math.round(afterDiscountCents * (order.taxPercent / 100));
  const totalCents = afterDiscountCents + taxCents;

  return { subtotalCents, discountCents, taxCents, totalCents };
}

/**
 * Format cents as a locale currency string.
 */
export function formatCents(cents: number, locale = 'en-US', currency = 'USD'): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
  }).format(cents / 100);
}

/**
 * Validate an order line — returns an error message or null.
 */
export function validateOrderLine(line: OrderLine): string | null {
  if (!line.productId || line.productId.trim() === '') {
    return 'productId must not be empty';
  }
  if (!Number.isInteger(line.quantity) || line.quantity <= 0) {
    return 'quantity must be a positive integer';
  }
  if (!Number.isInteger(line.unitPriceCents) || line.unitPriceCents < 0) {
    return 'unitPriceCents must be a non-negative integer';
  }
  return null;
}
