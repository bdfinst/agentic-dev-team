import type { Order } from "../../domain/order";

export interface OrderRepository {
  save(order: Order): Promise<void>;
}
