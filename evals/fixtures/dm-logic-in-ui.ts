// FAIL: Business rules implemented in the UI/controller layer

import { Request, Response } from "express";

interface CartItem {
  productId: string;
  name: string;
  priceCents: number;
  quantity: number;
  weight: number;
}

// Issue 1: Pricing rules embedded in a route handler
export async function checkoutHandler(req: Request, res: Response) {
  const cart: CartItem[] = req.body.items;
  const promoCode: string | undefined = req.body.promoCode;

  // Business rule: quantity discount tiers
  let subtotal = 0;
  for (const item of cart) {
    let unitPrice = item.priceCents;
    if (item.quantity >= 100) unitPrice = Math.round(unitPrice * 0.8);
    else if (item.quantity >= 25) unitPrice = Math.round(unitPrice * 0.9);
    else if (item.quantity >= 10) unitPrice = Math.round(unitPrice * 0.95);
    subtotal += unitPrice * item.quantity;
  }

  // Issue 2: Promo code validation logic in controller
  if (promoCode === "SUMMER25") {
    subtotal = Math.round(subtotal * 0.75);
  } else if (promoCode === "WELCOME10") {
    subtotal = Math.round(subtotal * 0.9);
  } else if (promoCode && promoCode !== "") {
    return res.status(400).json({ error: "Invalid promo code" });
  }

  // Issue 3: Shipping cost calculation in controller
  const totalWeight = cart.reduce((w, i) => w + i.weight * i.quantity, 0);
  let shippingCents: number;
  if (totalWeight <= 1) shippingCents = 499;
  else if (totalWeight <= 5) shippingCents = 999;
  else if (totalWeight <= 20) shippingCents = 1999;
  else shippingCents = 1999 + Math.ceil((totalWeight - 20) / 5) * 500;

  if (subtotal >= 10000) shippingCents = 0; // free shipping threshold

  // Issue 4: Authorization check inlined in handler
  const user = (req as any).user;
  const isAllowedToOrder =
    user.role === "admin" ||
    (user.role === "member" && user.accountStatus === "active") ||
    (user.role === "guest" && subtotal < 50000);

  if (!isAllowedToOrder) {
    return res.status(403).json({ error: "Not authorized to place this order" });
  }

  const total = subtotal + shippingCents;
  return res.json({ subtotal, shippingCents, total });
}
