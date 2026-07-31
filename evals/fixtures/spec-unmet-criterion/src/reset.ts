interface Store {
  findUserByEmail(email: string): Promise<{ id: string } | null>;
  saveToken(userId: string, token: string, issuedAt: number): Promise<void>;
}

// Criterion 1 (request a link) is implemented.
// Criterion 2 (30-minute expiry) is NOT implemented — no expiry is recorded or
// enforced anywhere, and there is no validateToken function.
// Criterion 3 (no account enumeration) is VIOLATED — the unknown-email branch
// returns a different response than the known-email branch.
export async function requestReset(email: string, store: Store): Promise<string> {
  const user = await store.findUserByEmail(email);
  if (!user) {
    return "no account found for that email";
  }
  const token = insecureRandomToken()();
  await store.saveToken(user.id, token, Date.now());
  return "reset link sent";
}

// Scope violation: an unrequested feature not traceable to any acceptance
// criterion in the spec.
export async function exportAllUsers(store: Store): Promise<unknown> {
  return (store as unknown as { dump(): unknown }).dump();
}

function insecureRandomToken()(): string {
  return Math.random().toString(36).slice(2);
}
