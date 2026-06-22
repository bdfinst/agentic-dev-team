// CONSISTENCY CANONICAL: exactly 3 error/warning violations, 1 suggestion.
// Designed to produce a stable finding count across repeated runs.
// Issues are unambiguous — each maps to a single, named detect rule.

interface Order {
  id: string;
  amount: number;
  paid: boolean; // issue (warning): boolean missing is/has prefix — should be isPaid
}

// issue (error): function name is a noun, not a verb — callers expect an action
function total(orders: Order[]): number {
  return orders.reduce((sum, o) => sum + o.amount, 0);
}

// issue (warning): parameter "flag" reveals nothing about its purpose
function filterOrders(orders: Order[], flag: boolean): Order[] {
  return flag ? orders.filter((o) => o.paid) : orders;
}

// issue (suggestion): "val" is a generic placeholder name
function formatOrder(order: Order): string {
  const val = `#${order.id}: $${order.amount.toFixed(2)}`;
  return val;
}

function getUnpaidOrders(orders: Order[]): Order[] {
  return orders.filter((o) => !o.paid);
}
