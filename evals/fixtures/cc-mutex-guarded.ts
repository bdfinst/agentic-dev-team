// NEGATIVE fixture — correct, concurrency-safe code with nothing to flag.
//
// The entire read-modify-write executes inside the mutex, and — critically —
// there is NO await, no promise, and no other suspension point anywhere between
// `m.acquire()` and `m.release()`. The critical section is straight-line
// synchronous code, so once a caller holds the mutex it runs the read and the
// write to completion before any other caller can acquire. The lock is always
// released in `finally`, so it is never leaked on a throw.
//
// There is no check-then-act gap, no lost update, no unawaited async, and no
// lock leak. A concurrency reviewer should find zero issues here.
interface Mutex {
  acquire(): Promise<void>;
  release(): void;
}

const counters = new Map<string, number>();

export async function safeIncrement(m: Mutex, key: string): Promise<void> {
  await m.acquire();
  try {
    // Fully synchronous critical section — no `await` between the read and the
    // write, so the increment is atomic with respect to every other holder of
    // this mutex. Callers serialize; no increment can be lost.
    const current = counters.get(key) ?? 0;
    counters.set(key, current + 1);
  } finally {
    // Always released, even if the body throws — no lock leak.
    m.release();
  }
}
