import { Pool } from "pg";

const LOOKUP_TIMEOUT_MS = 3_000;
const CONNECT_TIMEOUT_MS = 2_000;
const QUERY_TIMEOUT_MS = 5_000;
const POOL_SIZE = 10;
const CACHE_LIMIT = 1_000;
const HEARTBEAT_INTERVAL_MS = 30_000;

interface Order {
  id: string;
  customerId: string;
}

interface Customer {
  id: string;
  name: string;
}

class BoundedCache<V> {
  private readonly entries = new Map<string, V>();

  constructor(private readonly limit: number) {}

  get(key: string): V | undefined {
    const value = this.entries.get(key);
    if (value !== undefined) {
      this.entries.delete(key);
      this.entries.set(key, value);
    }
    return value;
  }

  set(key: string, value: V): void {
    this.entries.delete(key);
    this.entries.set(key, value);
    if (this.entries.size > this.limit) {
      const oldest = this.entries.keys().next().value as string;
      this.entries.delete(oldest);
    }
  }
}

const customerCache = new BoundedCache<Customer>(CACHE_LIMIT);

export const pool = new Pool({
  max: POOL_SIZE,
  connectionTimeoutMillis: CONNECT_TIMEOUT_MS,
  statement_timeout: QUERY_TIMEOUT_MS,
  query_timeout: QUERY_TIMEOUT_MS,
});

export async function enrichOrders(orders: readonly Order[]) {
  const missing = [...new Set(orders.map((o) => o.customerId))].filter(
    (id) => customerCache.get(id) === undefined,
  );
  if (missing.length > 0) {
    const client = await pool.connect();
    try {
      const { rows } = await client.query<Customer>(
        "SELECT id, name FROM customers WHERE id = ANY($1)",
        [missing],
      );
      rows.forEach((row) => customerCache.set(row.id, row));
    } finally {
      client.release();
    }
  }
  return orders.map((order) => ({ order, customer: customerCache.get(order.customerId) ?? null }));
}

export async function fetchProfile(url: string): Promise<unknown> {
  const response = await fetch(url, { signal: AbortSignal.timeout(LOOKUP_TIMEOUT_MS) });
  if (!response.ok) {
    throw new Error(`profile request failed: ${response.status}`);
  }
  return response.json();
}

export function startHeartbeat(): () => void {
  let inFlight = false;
  const timer = setInterval(() => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    pool
      .query("SELECT 1")
      .catch(() => undefined)
      .finally(() => {
        inFlight = false;
      });
  }, HEARTBEAT_INTERVAL_MS);
  return () => clearInterval(timer);
}
