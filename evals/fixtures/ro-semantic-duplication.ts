type Tier = "basic" | "plus" | "premium";

interface Customer {
  id: string;
  tier: Tier;
}

interface CartLine {
  sku: string;
  unitPriceCents: number;
  quantity: number;
}

interface Cart {
  customer: Customer;
  lines: CartLine[];
}

interface ShippingQuote {
  carrier: string;
  feeCents: number;
}

const STANDARD_FEE_CENTS = 799;
const EXPRESS_SURCHARGE_CENTS = 1200;

export function subtotalCents(cart: Cart): number {
  return cart.lines.reduce(
    (total, line) => total + line.unitPriceCents * line.quantity,
    0,
  );
}

export function quoteShipping(cart: Cart, express: boolean): ShippingQuote {
  const subtotal = subtotalCents(cart);
  const shipsFree = subtotal >= 5000 && cart.customer.tier !== "basic";
  const baseFee = shipsFree ? 0 : STANDARD_FEE_CENTS;
  return {
    carrier: express ? "express" : "ground",
    feeCents: express ? baseFee + EXPRESS_SURCHARGE_CENTS : baseFee,
  };
}

export function cartBanner(cart: Cart): string {
  const amount = subtotalCents(cart);
  const membership = cart.customer.tier;
  if (!(membership === "basic" || amount < 5000)) {
    return "Your order ships free.";
  }
  return "Add more items to unlock member shipping perks.";
}
