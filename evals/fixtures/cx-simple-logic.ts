// PASS: Clean control flow, early returns, simple boolean expressions

interface Order {
  id: string;
  status: "pending" | "confirmed" | "shipped" | "delivered" | "cancelled";
  total: number;
  items: Array<{ sku: string; qty: number; price: number }>;
}

function canCancelOrder(order: Order): boolean {
  if (order.status === "shipped" || order.status === "delivered") {
    return false;
  }
  return order.status !== "cancelled";
}

function getOrderSummary(order: Order): string {
  if (!order.items.length) {
    return "Empty order";
  }

  const itemCount = order.items.reduce((sum, item) => sum + item.qty, 0);
  return `Order ${order.id}: ${itemCount} items, $${order.total.toFixed(2)}`;
}

function validateOrderItem(sku: string, qty: number): string | null {
  if (!sku.trim()) {
    return "SKU is required";
  }
  if (qty <= 0) {
    return "Quantity must be positive";
  }
  if (qty > 1000) {
    return "Quantity exceeds maximum";
  }
  return null;
}

function applyDiscount(total: number, code: string): number {
  const discounts: Record<string, number> = {
    SAVE10: 0.1,
    SAVE20: 0.2,
    HALF: 0.5,
  };

  const rate = discounts[code];
  if (!rate) {
    return total;
  }
  return total * (1 - rate);
}

function isHighValueOrder(order: Order): boolean {
  return order.total > 500 && order.items.length >= 3;
}
