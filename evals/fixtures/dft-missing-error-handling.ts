// Use case: "place order". Traced across controller -> service -> external
// payment gateway. GAP: the external payment call has no timeout, no retry, and
// no fallback, and its rejection is not caught anywhere in the flow — an outage
// or slow response in the payment gateway hangs or crashes the whole request.

interface PaymentClient {
  // Network call to a third-party payment gateway. No timeout is configurable
  // here and the caller never wraps it.
  charge(customerId: string, amountCents: number): Promise<{ id: string }>;
}

interface OrderRepo {
  insert(order: { customerId: string; amountCents: number; paymentId: string }): Promise<void>;
}

// Service layer.
async function placeOrder(
  payment: PaymentClient,
  orders: OrderRepo,
  customerId: string,
  amountCents: number,
): Promise<string> {
  // GAP: external call with no timeout / retry / fallback and no surrounding
  // try/catch. If `charge` rejects or hangs, this promise rejects unhandled and
  // the order write below never runs — the failure has no controlled path.
  const receipt = await payment.charge(customerId, amountCents);
  await orders.insert({ customerId, amountCents, paymentId: receipt.id });
  return receipt.id;
}

// Controller layer — passes the request straight through with no error boundary.
export async function postOrder(
  payment: PaymentClient,
  orders: OrderRepo,
  req: { customerId: string; amountCents: number },
): Promise<{ paymentId: string }> {
  const paymentId = await placeOrder(payment, orders, req.customerId, req.amountCents);
  return { paymentId };
}
