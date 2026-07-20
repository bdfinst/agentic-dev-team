// Check-then-act on shared balances with an await between the check and the
// write: two concurrent withdrawals both pass the balance check before either
// decrements, so the account overdraws (lost update / TOCTOU).
const balances = new Map<string, number>();

async function persist(id: string, value: number): Promise<void> {
  // async flush to storage
}

export async function withdraw(accountId: string, amount: number): Promise<void> {
  const current = balances.get(accountId) ?? 0;
  if (current < amount) {
    throw new Error("insufficient funds");
  }
  // BUG: the await suspends here. A second concurrent withdrawal reads the same
  // `current`, passes the same check, and both write `current - amount` — the
  // two withdrawals collapse into one and the balance can go negative.
  await persist(accountId, current);
  balances.set(accountId, current - amount);
}
