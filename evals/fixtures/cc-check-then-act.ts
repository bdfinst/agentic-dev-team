// Check-then-act race on a shared balance with an await BETWEEN the check and
// the write. This is the textbook TOCTOU / lost-update bug: the balance read
// and the balance write are separated by a suspension point, so two concurrent
// withdrawals both observe the same starting balance, both pass the same check,
// and both write a decrement computed from that one stale read.
const balances = new Map<string, number>();

async function persist(id: string, value: number): Promise<void> {
  // async flush to durable storage — this is the suspension point
}

export async function withdraw(accountId: string, amount: number): Promise<void> {
  // 1. CHECK — read the balance and validate it.
  const current = balances.get(accountId) ?? 0;
  if (current < amount) {
    throw new Error("insufficient funds");
  }

  // 2. await SUSPENDS here. While this withdrawal is parked, a second
  //    concurrent withdrawal runs steps 1-2 against the SAME `current`: it
  //    reads the identical starting balance and passes the identical check,
  //    because nothing has been written back yet.
  await persist(accountId, current - amount);

  // 3. ACT — write a value computed from the stale `current` captured before
  //    the await. Both withdrawals write `current - amount`, so two debits
  //    collapse into one and the account can be overdrawn.
  balances.set(accountId, current - amount);
}
