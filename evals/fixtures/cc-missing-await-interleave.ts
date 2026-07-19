// A mutation is fired without await, so a later read can interleave with the
// still-pending write and observe stale state.
interface Store {
  set(k: string, v: number): Promise<void>;
  get(k: string): Promise<number>;
}

let store: Store;

export async function bumpAndReport(key: string): Promise<number> {
  const current = await store.get(key);
  // BUG: the set is not awaited, so it is still in flight when we read below.
  store.set(key, current + 1);
  // Races the pending write; frequently returns the pre-increment value.
  return store.get(key);
}
