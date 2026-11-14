import type { Pool } from "pg";
import type { Order } from "../../domain/order";
import type { OrderRepository } from "../../application/ports/order-repository.port";

export class PgOrderRepository implements OrderRepository {
  constructor(private readonly pool: Pool) {}

  async save(order: Order): Promise<void> {
    await this.pool.query(
      "INSERT INTO orders (id, customer_id, status, tax_cents, lines) VALUES ($1, $2, $3, $4, $5)",
      [order.id, order.customerId, order.status, order.taxCents, JSON.stringify(order.lines)],
    );
  }
}
