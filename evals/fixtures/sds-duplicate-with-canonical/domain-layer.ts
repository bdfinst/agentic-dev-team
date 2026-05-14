// SKILL: semantic-duplication-scan
// LAYER: domain (expected)
// ROLE: canonical copy — no infrastructure imports

function applyDiscount(basePrice: number, discountRate: number): number {
  if (discountRate < 0 || discountRate > 1) {
    throw new Error("discountRate must be between 0 and 1");
  }
  return basePrice * (1 - discountRate);
}
