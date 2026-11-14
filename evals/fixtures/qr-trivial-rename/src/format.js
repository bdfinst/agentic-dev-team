export function formatPrice(cents) {
  const dollars = (cents / 100).toFixed(2);
  return `$${dollars}`;
}
