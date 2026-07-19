// Concurrent read-modify-write on a shared Map entry with an await in the
// middle: two callers read the same counter and one increment is lost.
const counters = new Map<string, number>();

async function persist(key: string, value: number): Promise<void> {
  // async flush to storage
}

export async function increment(key: string): Promise<void> {
  const current = counters.get(key) ?? 0;
  // BUG: the await yields; a concurrent increment reads the same current value,
  // so the two writes below collapse into a single effective increment.
  await persist(key, current + 1);
  counters.set(key, current + 1);
}
