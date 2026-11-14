interface Mutex {
  runExclusive<T>(work: () => Promise<T>): Promise<T>;
}

interface StockStore {
  getAvailable(sku: string): Promise<number>;
  setAvailable(sku: string, quantity: number): Promise<void>;
}

export class ReservationService {
  constructor(
    private readonly store: StockStore,
    private readonly lockFor: (sku: string) => Mutex,
  ) {}

  async reserve(sku: string, quantity: number): Promise<boolean> {
    return this.lockFor(sku).runExclusive(async () => {
      const available = await this.store.getAvailable(sku);
      if (available < quantity) {
        return false;
      }
      await this.store.setAvailable(sku, available - quantity);
      return true;
    });
  }

  async release(sku: string, quantity: number): Promise<void> {
    const available = await this.store.getAvailable(sku);
    await this.store.setAvailable(sku, available + quantity);
  }

  async availability(skus: readonly string[]): Promise<Map<string, number>> {
    const counts = await Promise.all(skus.map((sku) => this.store.getAvailable(sku)));
    return new Map(skus.map((sku, index) => [sku, counts[index]]));
  }
}
