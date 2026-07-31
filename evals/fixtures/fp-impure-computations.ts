// FAIL: Side effects buried inside otherwise value-returning computations

declare function fetch(url: string): Promise<{ json(): Promise<unknown> }>;
declare const document: { querySelector(sel: string): { textContent: string | null } | null };

function computeDiscountedPrice(price: number, pct: number): number {
  console.log(`discounting ${price} by ${pct}%`); // buried side effect: logging
  return price * (1 - pct / 100);
}

function readRoundedTotal(): number {
  const el = document.querySelector("#total"); // buried side effect: DOM access
  const raw = el ? Number(el.textContent) : 0;
  return Math.round(raw * 100) / 100;
}

async function loadClampedUserScore(userId: string): Promise<number> {
  const res = await fetch(`/api/users/${encodeURIComponent(userId)}/score`); // buried side effect: network call
  const data = (await res.json()) as { score: number };
  return Math.min(100, Math.max(0, data.score));
}

function generateRequestId(): string {
  return `req-${Math.random()}`; // buried side effect: non-determinism (illustrative only, not a security token)
}

function timestampedLabel(prefix: string): string {
  return `${prefix}-${new Date().toISOString()}`; // buried side effect: non-determinism
}

export {
  computeDiscountedPrice,
  readRoundedTotal,
  loadClampedUserScore,
  generateRequestId,
  timestampedLabel,
};
