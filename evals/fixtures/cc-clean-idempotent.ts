// Concurrency-safe by construction: no shared mutable module state, every async
// operation is awaited with error handling, and mutations are idempotent.

interface Store {
  get(key: string): Promise<unknown>;
  put(key: string, value: unknown): Promise<void>;
}
interface Profile {
  displayName: string;
}
interface Dashboard {
  profile: unknown;
  settings: unknown;
  notifications: unknown;
}

declare function logError(message: string, err: unknown): void;

// Idempotent by construction: a full-resource PUT keyed by id yields the same
// state on retry, so a duplicated/retried request is safe with no dedup needed.
// No shared mutable state; the async op is awaited and errors propagate.
export async function upsertProfile(store: Store, id: string, profile: Profile): Promise<void> {
  try {
    await store.put(`profile:${id}`, profile);
  } catch (err) {
    logError("upsertProfile failed", err);
    throw err;
  }
}

// Independent parallel reads with no shared writes; the Promise.all is awaited,
// so a rejection is not swallowed and there is no fire-and-forget path.
export async function loadDashboard(store: Store, userId: string): Promise<Dashboard> {
  const [profile, settings, notifications] = await Promise.all([
    store.get(`profile:${userId}`),
    store.get(`settings:${userId}`),
    store.get(`notifications:${userId}`),
  ]);
  return { profile, settings, notifications };
}
