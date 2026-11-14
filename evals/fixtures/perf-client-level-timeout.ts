import axios from "axios";

const INVENTORY_TIMEOUT_MS = 2_500;
const RESERVATION_TTL_MS = 10 * 60_000;
const SWEEP_INTERVAL_MS = 60_000;

const inventoryApi = axios.create({
  baseURL: process.env.INVENTORY_URL,
  timeout: INVENTORY_TIMEOUT_MS,
});

interface Reservation {
  sku: string;
  quantity: number;
  expiresAt: number;
}

interface StockLevel {
  sku: string;
  available: number;
}

export class ReservationBook {
  private readonly reservations = new Map<string, Reservation>();
  private sweeper: ReturnType<typeof setInterval> | undefined;

  start(): void {
    this.sweeper = setInterval(() => this.sweep(Date.now()), SWEEP_INTERVAL_MS);
  }

  stop(): void {
    clearInterval(this.sweeper);
    this.sweeper = undefined;
  }

  reserve(cartId: string, sku: string, quantity: number, now: number): void {
    this.reservations.set(cartId, { sku, quantity, expiresAt: now + RESERVATION_TTL_MS });
  }

  release(cartId: string): void {
    this.reservations.delete(cartId);
  }

  private sweep(now: number): void {
    for (const [cartId, reservation] of this.reservations) {
      if (reservation.expiresAt <= now) {
        this.reservations.delete(cartId);
      }
    }
  }
}

export async function stockFor(skus: readonly string[]): Promise<Map<string, number>> {
  const { data } = await inventoryApi.get<StockLevel[]>("/stock", {
    params: { skus: skus.join(",") },
  });
  const levels = new Map(data.map((level) => [level.sku, level.available]));
  const result = new Map<string, number>();
  for (const sku of skus) {
    result.set(sku, levels.get(sku) ?? 0);
  }
  return result;
}

export async function confirmOrder(orderId: string): Promise<void> {
  await inventoryApi.post(`/orders/${orderId}/confirm`);
}
