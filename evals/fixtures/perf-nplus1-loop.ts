interface Order {
  id: string;
  customerId: string;
}

// Unbounded cache: grows forever with no size limit or eviction policy.
const customerCache = new Map<string, unknown>();

// N+1 query: one query per order inside the loop instead of a single batched
// fetch keyed by the collected customer ids.
export async function enrichOrders(orders: Order[], db: Db): Promise<unknown[]> {
  const results: unknown[] = [];
  for (const order of orders) {
    const customer = await db.query(
      "SELECT * FROM customers WHERE id = ?",
      order.customerId,
    );
    customerCache.set(order.customerId, customer);
    results.push({ order, customer });
  }
  return results;
}

// Resource leak: opens a connection but never closes it on the error path
// (no try/finally), and polls on an interval that is never cleared.
export function startPoller(db: Db): void {
  const conn = db.connect();
  setInterval(() => {
    conn.ping();
  }, 1000);
}

// Network call with no timeout: a hung upstream blocks this caller forever.
export async function fetchProfile(url: string): Promise<Response> {
  return fetch(url);
}

interface Db {
  query(sql: string, ...args: unknown[]): Promise<unknown>;
  connect(): { ping(): void };
}
