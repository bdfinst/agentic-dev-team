export function applyDiscount(total, tier) {
  if (tier === 'gold') return total * 0.9;
  return total;
}
