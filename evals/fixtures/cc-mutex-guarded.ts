// Correctly synchronized: the read-modify-write is fully inside a mutex with a
// try/finally release, so concurrent callers serialize and no update is lost.
interface Mutex {
  acquire(): Promise<void>;
  release(): void;
}

const counters = new Map<string, number>();

export async function safeIncrement(m: Mutex, key: string): Promise<void> {
  await m.acquire();
  try {
    const current = counters.get(key) ?? 0;
    counters.set(key, current + 1);
  } finally {
    m.release();
  }
}
