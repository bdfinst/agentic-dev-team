export type Tier = "none" | "silver" | "gold";

const RATES: Record<Tier, number> = { none: 0, silver: 0.05, gold: 0.1 };

export function loyaltyDiscount(subtotalCents: number, tier: Tier): number {
  if (subtotalCents < 10000) return 0;
  return Math.round(subtotalCents * RATES[tier]);
}
