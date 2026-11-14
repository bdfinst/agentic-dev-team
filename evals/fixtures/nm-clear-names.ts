const HIGH_VALUE_ORDER_THRESHOLD = 500;
const PRIORITY_HANDLING_LABEL = "Priority handling";
const STANDARD_HANDLING_LABEL = "Standard handling";
const GIFT_WRAPPED_LABEL = "Gift wrapped";

interface ShippingAddress {
  streetLine1: string;
  streetLine2?: string;
  city: string;
  stateCode: string;
  postalCode: string;
  countryCode: string;
}

interface OrderItem {
  productId: string;
  productName: string;
  unitPrice: number;
  quantity: number;
}

interface Order {
  orderId: string;
  items: OrderItem[];
  shippingAddress: ShippingAddress;
  isGiftWrapped: boolean;
  hasExpressShipping: boolean;
}

function calculateOrderTotal(items: OrderItem[]): number {
  return items.reduce(
    (runningTotal, item) => runningTotal + item.unitPrice * item.quantity,
    0,
  );
}

function formatShippingLabel(address: ShippingAddress): string {
  const addressLines = [
    address.streetLine1,
    address.streetLine2,
    `${address.city}, ${address.stateCode} ${address.postalCode}`,
    address.countryCode,
  ];

  const presentLines = addressLines.filter(
    (line): line is string => line !== undefined,
  );

  return presentLines.join("\n");
}

function findExpressOrdersWithItems(orders: Order[]): Order[] {
  return orders.filter(
    (order) => order.hasExpressShipping && order.items.length > 0,
  );
}

function buildOrderSummary(order: Order): string {
  const totalAmount = calculateOrderTotal(order.items);
  const isHighValue = totalAmount > HIGH_VALUE_ORDER_THRESHOLD;
  const itemCount = order.items.length;

  const summaryParts = [
    `Order ${order.orderId}: ${itemCount} items`,
    `Total: $${totalAmount.toFixed(2)}`,
    isHighValue ? PRIORITY_HANDLING_LABEL : STANDARD_HANDLING_LABEL,
    order.isGiftWrapped ? GIFT_WRAPPED_LABEL : "",
  ];

  return summaryParts.filter(Boolean).join(" | ");
}

export {
  calculateOrderTotal,
  formatShippingLabel,
  findExpressOrdersWithItems,
  buildOrderSummary,
};
