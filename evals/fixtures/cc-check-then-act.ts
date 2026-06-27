// Shared mutable state mutated from multiple concurrent async paths.
const balances = new Map<string, number>();

// Read-then-write without atomicity: two concurrent withdrawals can both pass
// the check before either decrements, overdrawing the account (lost update).
export async function withdraw(accountId: string, amount: number): Promise<void> {
  const current = balances.get(accountId) ?? 0;
  if (current < amount) {
    throw new Error("insufficient funds");
  }
  await persist(accountId, current); // suspension point widens the race window
  balances.set(accountId, current - amount);
}

// Non-idempotent handler: a retried request charges the card twice because there
// is no idempotency key or deduplication.
export async function handleCharge(req: { cardId: string; cents: number }): Promise<void> {
  await chargeCard(req.cardId, req.cents);
  await sendReceipt(req.cardId);
}

// Fire-and-forget promise: the rejection is unhandled, so a failed flush is
// silently swallowed.
export function scheduleFlush(): void {
  flushQueue();
}

async function persist(_id: string, _v: number): Promise<void> {}
async function chargeCard(_id: string, _cents: number): Promise<void> {}
async function sendReceipt(_id: string): Promise<void> {}
async function flushQueue(): Promise<void> {}
