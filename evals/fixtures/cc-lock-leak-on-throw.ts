// A mutex is acquired but only released on the success path; if the guarded
// work throws, the lock is never released and every future acquirer deadlocks.
interface Mutex {
  acquire(): Promise<void>;
  release(): void;
}

export async function withBalanceUpdate(
  m: Mutex,
  apply: () => Promise<void>,
): Promise<void> {
  await m.acquire();
  // BUG: no try/finally — if apply() rejects, release() never runs and the
  // lock is leaked forever.
  await apply();
  m.release();
}
