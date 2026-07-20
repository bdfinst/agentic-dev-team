// Contract: resolve to the processed result for EVERY item. This is a
// fire-and-forget bug: the loop starts an async task per item but never awaits
// it and never collects the promises, and the function returns the shared array
// synchronously — before a single task has resolved. Two independent defects
// make it unmistakable:
//   1. the promises are neither awaited nor gathered (no `await`, no Promise.all),
//      so `return` runs while every task is still pending; and
//   2. results accumulate into a module-level array shared across calls, so
//      concurrent invocations interleave their pushes and corrupt each other.
const collected: string[] = [];

async function process(item: string): Promise<string> {
  // async work — resolves on a later tick, after processAll has already returned
  return item;
}

export async function processAll(items: string[]): Promise<string[]> {
  collected.length = 0;
  for (const item of items) {
    // BUG: started and dropped. The returned promise is not awaited and not
    // pushed into any array to await later — it is pure fire-and-forget.
    void process(item).then((r) => collected.push(r));
  }
  // BUG: returns the shared array NOW, before any `.then` callback above has run,
  // so callers reliably receive an empty (or partially filled) result.
  return collected;
}
