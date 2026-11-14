import { describe, it, expect, beforeEach } from "vitest";

type Plan = "monthly" | "annual";

interface Subscription {
  readonly id: string;
  readonly plan: Plan;
  readonly startedOn: string; // ISO date, UTC
  readonly status: "active" | "cancelled";
}

interface SubscriptionStore {
  find(id: string): Promise<Subscription | undefined>;
  save(subscription: Subscription): Promise<void>;
}

interface Clock {
  today(): string; // ISO date, UTC
}

const ANNUAL_REFUND_WINDOW_DAYS = 30;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

class SubscriptionService {
  constructor(
    private readonly store: SubscriptionStore,
    private readonly clock: Clock,
  ) {}

  async cancel(id: string): Promise<{ refundable: boolean }> {
    const subscription = await this.store.find(id);
    if (!subscription) {
      throw new Error(`Subscription ${id} not found`);
    }
    if (subscription.status === "cancelled") {
      throw new Error(`Subscription ${id} is already cancelled`);
    }
    await this.store.save({ ...subscription, status: "cancelled" });
    return { refundable: this.isRefundable(subscription) };
  }

  private isRefundable(subscription: Subscription): boolean {
    if (subscription.plan === "monthly") return false;
    const elapsedDays =
      (Date.parse(this.clock.today()) - Date.parse(subscription.startedOn)) /
      MS_PER_DAY;
    return elapsedDays <= ANNUAL_REFUND_WINDOW_DAYS;
  }
}

class InMemoryStore implements SubscriptionStore {
  private readonly rows = new Map<string, Subscription>();

  constructor(seed: Subscription[]) {
    seed.forEach((row) => this.rows.set(row.id, row));
  }

  async find(id: string) {
    return this.rows.get(id);
  }

  async save(subscription: Subscription) {
    this.rows.set(subscription.id, subscription);
  }
}

const fixedClock = (today: string): Clock => ({ today: () => today });

const annual = (startedOn: string): Subscription => ({
  id: "sub-annual",
  plan: "annual",
  startedOn,
  status: "active",
});

describe("SubscriptionService.cancel", () => {
  let store: InMemoryStore;

  beforeEach(() => {
    store = new InMemoryStore([
      annual("2026-03-01"),
      {
        id: "sub-monthly",
        plan: "monthly",
        startedOn: "2026-03-01",
        status: "active",
      },
      {
        id: "sub-done",
        plan: "annual",
        startedOn: "2026-01-01",
        status: "cancelled",
      },
    ]);
  });

  it("marks the subscription cancelled", async () => {
    const service = new SubscriptionService(store, fixedClock("2026-03-10"));

    await service.cancel("sub-annual");

    expect((await store.find("sub-annual"))?.status).toBe("cancelled");
  });

  it("refunds an annual plan cancelled on the last day of the 30-day window", async () => {
    // 2026-03-01 + 30 days = 2026-03-31
    const service = new SubscriptionService(store, fixedClock("2026-03-31"));

    const result = await service.cancel("sub-annual");

    expect(result).toEqual({ refundable: true });
  });

  it("does not refund an annual plan cancelled one day after the window", async () => {
    const service = new SubscriptionService(store, fixedClock("2026-04-01"));

    const result = await service.cancel("sub-annual");

    expect(result).toEqual({ refundable: false });
  });

  it("never refunds a monthly plan", async () => {
    const service = new SubscriptionService(store, fixedClock("2026-03-02"));

    const result = await service.cancel("sub-monthly");

    expect(result).toEqual({ refundable: false });
  });

  it("rejects an unknown subscription id", async () => {
    const service = new SubscriptionService(store, fixedClock("2026-03-10"));

    await expect(service.cancel("sub-missing")).rejects.toThrow(
      "Subscription sub-missing not found",
    );
  });

  it("rejects a subscription that is already cancelled", () => {
    const service = new SubscriptionService(store, fixedClock("2026-03-10"));

    expect(service.cancel("sub-done")).rejects.toThrow(
      "Subscription sub-done is already cancelled",
    );
  });
});
