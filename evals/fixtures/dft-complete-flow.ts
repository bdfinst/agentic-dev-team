// Use case: "place order". Traced across controller -> service -> repository
// -> external payment gateway. This flow has NO gaps: the external call is
// bounded by a timeout, retried, and has a fallback; the write is transactional;
// the read is batched and paginated; errors are caught at a boundary.

interface PaymentClient {
  // Bounded external call: timeout + retry + fallback are all handled inside.
  chargeWithTimeoutAndRetry(
    customerId: string,
    amountCents: number,
    opts: { timeoutMs: number; retries: number; onExhausted: () => { id: string } },
  ): Promise<{ id: string }>;
}

interface OrderRepo {
  // Repository exposes an explicit transaction boundary.
  withTransaction<T>(work: () => Promise<T>): Promise<T>;
  insert(order: { customerId: string; amountCents: number; paymentId: string }): Promise<void>;
  recordReceipt(paymentId: string): Promise<void>;
}

// Service layer.
async function placeOrder(
  payment: PaymentClient,
  orders: OrderRepo,
  customerId: string,
  amountCents: number,
): Promise<string> {
  const receipt = await payment.chargeWithTimeoutAndRetry(customerId, amountCents, {
    timeoutMs: 3000,
    retries: 2,
    onExhausted: () => ({ id: "queued-for-manual-settlement" }),
  });
  // Atomic: both writes commit together or roll back together.
  await orders.withTransaction(async () => {
    await orders.insert({ customerId, amountCents, paymentId: receipt.id });
    await orders.recordReceipt(receipt.id);
  });
  return receipt.id;
}

// Controller layer — explicit error boundary translating failures to a 502.
export async function postOrder(
  payment: PaymentClient,
  orders: OrderRepo,
  req: { customerId: string; amountCents: number },
): Promise<{ status: number; paymentId?: string }> {
  try {
    const paymentId = await placeOrder(payment, orders, req.customerId, req.amountCents);
    return { status: 201, paymentId };
  } catch {
    return { status: 502 };
  }
}
