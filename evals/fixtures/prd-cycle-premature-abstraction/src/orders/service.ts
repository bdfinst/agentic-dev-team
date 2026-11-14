import { dispatch } from "../notifications/dispatcher";
import type { OrderRepository } from "./repository";
import type { Order } from "./types";

export class OrderService {
  constructor(private readonly orders: OrderRepository) {}

  async place(order: Order): Promise<Order> {
    const saved = await this.orders.insert(order);
    await dispatch({ kind: "order-placed", customerId: saved.customerId, orderId: saved.id });
    return saved;
  }

  async listForCustomer(customerId: string, since: Date): Promise<Order[]> {
    return this.orders.findByCustomer(customerId, since);
  }
}
