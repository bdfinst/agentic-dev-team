// An at-least-once message handler applies a monetary side effect with no
// idempotency key or dedup: a redelivered / retried message double-charges.
interface Payments {
  charge(account: string, cents: number): Promise<void>;
}

interface Msg {
  id: string;
  account: string;
  cents: number;
}

export async function handlePayment(pay: Payments, msg: Msg): Promise<void> {
  // BUG: nothing records that msg.id was already processed. Under at-least-once
  // delivery (the default for most brokers) a retry runs charge() a second time.
  await pay.charge(msg.account, msg.cents);
}
