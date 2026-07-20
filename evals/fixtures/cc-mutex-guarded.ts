// Correctly synchronized and concurrency-safe: the entire read-modify-write runs
// inside the mutex with NO await between the read and the write, and the lock is
// always released in finally. Concurrent callers serialize, so no update is lost
// and there is nothing to flag.
interface Mutex {
  acquire(): Promise<void>;
  release(): void;
}

const counters = new Map<string, number>();

export async function safeIncrement(m: Mutex, key: string): Promise<void> {
  await m.acquire();
  try {
    // Critical section is fully synchronous — no suspension point between the
    // read and the write, so the increment is atomic with respect to any other
    // holder of this mutex.
    const current = counters.get(key) ?? 0;
    counters.set(key, current + 1);
  } finally {
    m.release();
  }
}
