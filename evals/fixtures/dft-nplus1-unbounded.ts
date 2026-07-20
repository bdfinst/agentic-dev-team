// Use case: "list orders with their line items". Traced across service ->
// repository -> database. Two GAPS: (1) an N+1 query pattern — one query for the
// orders, then one more query per order inside the loop; (2) the order query is
// unbounded — no LIMIT / pagination, so a large customer streams every row.

interface Db {
  query<T>(sql: string, params?: unknown[]): Promise<T[]>;
}

interface Order {
  id: string;
  customerId: string;
}

interface LineItem {
  orderId: string;
  sku: string;
}

// Repository layer.
async function listOrdersWithItems(db: Db, customerId: string): Promise<
  { order: Order; items: LineItem[] }[]
> {
  // GAP: unbounded result set — selects every order for the customer with no
  // LIMIT and no pagination cursor.
  const orders = await db.query<Order>(
    "SELECT id, customer_id FROM orders WHERE customer_id = $1",
    [customerId],
  );

  const result: { order: Order; items: LineItem[] }[] = [];
  for (const order of orders) {
    // GAP: N+1 — one additional query per order instead of a single joined or
    // batched (WHERE order_id IN (...)) fetch.
    const items = await db.query<LineItem>(
      "SELECT order_id, sku FROM line_items WHERE order_id = $1",
      [order.id],
    );
    result.push({ order, items });
  }
  return result;
}

// Service layer — returns the whole materialized list to the caller.
export async function getCustomerOrders(db: Db, customerId: string) {
  return listOrdersWithItems(db, customerId);
}
