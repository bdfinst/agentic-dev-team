import { subtotalCents, type Order, type OrderLine } from "../domain/order";
import type { OrderRepository } from "./ports/order-repository.port";
import type { TaxRates } from "./ports/tax-rates.port";

const FRAUD_REVIEW_THRESHOLD = 0.8;

export interface PlaceOrderCommand {
  orderId: string;
  customerId: string;
  shippingRegion: string;
  lines: OrderLine[];
}

export class PlaceOrder {
  constructor(
    private readonly taxRates: TaxRates,
    private readonly orders: OrderRepository,
  ) {}

  async execute(command: PlaceOrderCommand): Promise<Order> {
    const subtotal = subtotalCents(command);
    const rate = await this.taxRates.rateFor(command.shippingRegion);

    const fraudResponse = await fetch("https://risk.partner.example/v2/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customerId: command.customerId, amountCents: subtotal }),
    });
    const { score } = (await fraudResponse.json()) as { score: number };

    const order: Order = {
      id: command.orderId,
      customerId: command.customerId,
      shippingRegion: command.shippingRegion,
      lines: command.lines,
      taxCents: Math.round(subtotal * rate),
      status: score >= FRAUD_REVIEW_THRESHOLD ? "held-for-review" : "placed",
    };
    await this.orders.save(order);
    return order;
  }
}
