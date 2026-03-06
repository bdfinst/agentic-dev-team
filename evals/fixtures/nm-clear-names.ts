// PASS: Variables reveal intent, functions describe actions, booleans prefixed, collections pluralized.

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
  const subtotal = items.reduce(
    (runningTotal, item) => runningTotal + item.unitPrice * item.quantity,
    0,
  );
  return subtotal;
}

function formatShippingLabel(address: ShippingAddress): string {
  const addressLines = [
    address.streetLine1,
    address.streetLine2,
    `${address.city}, ${address.stateCode} ${address.postalCode}`,
    address.countryCode,
  ];

  const nonEmptyLines = addressLines.filter(
    (line): line is string => line !== undefined,
  );

  return nonEmptyLines.join("\n");
}

function findEligibleOrders(orders: Order[]): Order[] {
  const eligibleOrders = orders.filter(
    (order) => order.hasExpressShipping && order.items.length > 0,
  );
  return eligibleOrders;
}

function buildOrderSummary(order: Order): string {
  const totalAmount = calculateOrderTotal(order.items);
  const isHighValue = totalAmount > 500;
  const itemCount = order.items.length;

  const summaryParts = [
    `Order ${order.orderId}: ${itemCount} items`,
    `Total: $${totalAmount.toFixed(2)}`,
    isHighValue ? "Priority handling" : "Standard handling",
    order.isGiftWrapped ? "Gift wrapped" : "",
  ];

  return summaryParts.filter(Boolean).join(" | ");
}
