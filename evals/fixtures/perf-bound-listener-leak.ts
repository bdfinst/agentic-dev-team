import { EventEmitter } from "node:events";

const PRICE_FEED_TIMEOUT_MS = 5_000;
const MAX_TRACKED_SYMBOLS = 500;

interface Quote {
  symbol: string;
  price: number;
}

export class PriceWidget {
  private readonly latest = new Map<string, number>();

  constructor(
    private readonly feed: EventEmitter,
    private readonly render: (quotes: ReadonlyMap<string, number>) => void,
  ) {}

  mount(): void {
    this.feed.on("quote", this.onQuote.bind(this));
  }

  unmount(): void {
    this.feed.off("quote", this.onQuote.bind(this));
    this.latest.clear();
  }

  private onQuote(quote: Quote): void {
    if (!this.latest.has(quote.symbol) && this.latest.size >= MAX_TRACKED_SYMBOLS) {
      return;
    }
    this.latest.set(quote.symbol, quote.price);
    this.render(this.latest);
  }
}

export async function loadSnapshot(baseUrl: string, symbols: readonly string[]): Promise<Quote[]> {
  const query = new URLSearchParams({ symbols: symbols.join(",") });
  const response = await fetch(`${baseUrl}/quotes?${query}`, {
    signal: AbortSignal.timeout(PRICE_FEED_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`snapshot request failed: ${response.status}`);
  }
  return (await response.json()) as Quote[];
}
