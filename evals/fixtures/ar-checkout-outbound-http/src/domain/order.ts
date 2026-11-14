export interface OrderLine {
  readonly sku: string;
  readonly quantity: number;
  readonly unitPriceCents: number;
}

export interface Order {
  readonly id: string;
  readonly customerId: string;
  readonly shippingRegion: string;
  readonly lines: readonly OrderLine[];
  readonly taxCents: number;
  readonly status: "pending" | "placed" | "held-for-review";
}

export function subtotalCents(order: Pick<Order, "lines">): number {
  return order.lines.reduce((sum, line) => sum + line.quantity * line.unitPriceCents, 0);
}
