interface Money {
  readonly cents: number;
  readonly currency: string;
}

interface LineItem {
  readonly sku: string;
  readonly quantity: number;
  readonly unitPrice: Money;
}

interface Totals {
  subtotal: number;
  discount: number;
  tax: number;
}

interface Order {
  readonly id: string;
  readonly lines: readonly LineItem[];
  readonly totals: Totals;
  readonly couponCode: string | null;
}

const TAX_RATE = 0.08;
const COUPON_RATES: Readonly<Record<string, number>> = { SPRING10: 0.1, VIP20: 0.2 };

const lineTotal = (line: LineItem): number => line.quantity * line.unitPrice.cents;

const subtotalOf = (lines: readonly LineItem[]): number =>
  lines.reduce((sum, line) => sum + lineTotal(line), 0);

const sortedBySku = (lines: readonly LineItem[]): LineItem[] =>
  [...lines].sort((a, b) => a.sku.localeCompare(b.sku));

const withQuantity = (line: LineItem, quantity: number): LineItem => ({
  ...line,
  quantity,
});

const couponRate = (code: string | null): number =>
  code === null ? 0 : COUPON_RATES[code] ?? 0;

export const recalculate = (order: Order): Order => {
  const subtotal = subtotalOf(order.lines);
  const discount = Math.round(subtotal * couponRate(order.couponCode));
  return {
    ...order,
    totals: { subtotal, discount, tax: Math.round((subtotal - discount) * TAX_RATE) },
  };
};

export const applyCoupon = (order: Order, code: string): Order => {
  const next = { ...order, couponCode: code };
  next.totals.discount = Math.round(next.totals.subtotal * couponRate(code));
  next.totals.tax = Math.round((next.totals.subtotal - next.totals.discount) * TAX_RATE);
  return next;
};

export const changeQuantity = (order: Order, sku: string, quantity: number): Order =>
  recalculate({
    ...order,
    lines: order.lines.map((line) => (line.sku === sku ? withQuantity(line, quantity) : line)),
  });

export const removeLine = (order: Order, sku: string): Order =>
  recalculate({ ...order, lines: order.lines.filter((line) => line.sku !== sku) });

export const receiptLines = (order: Order): string[] =>
  sortedBySku(order.lines).map(
    (line) => `${line.sku} x${line.quantity} ${lineTotal(line)} ${line.unitPrice.currency}`,
  );
