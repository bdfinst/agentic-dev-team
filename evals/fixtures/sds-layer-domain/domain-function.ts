// SKILL: semantic-duplication-scan
// EXPECTED layer: "domain"
// REASON: no external imports, pure computation using only primitive types

function calculateOrderTotal(lineItems: Array<{ quantity: number; unitPrice: number }>): number {
  return lineItems.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
}
