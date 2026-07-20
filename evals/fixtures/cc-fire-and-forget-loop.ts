// Contract: return the processed result for every item. BUG: each task is
// started without await and pushed into a shared array that is returned
// immediately — before any task has completed — so callers receive a partial
// (usually empty) result, and concurrent calls corrupt each other through the
// shared array.
const collected: string[] = [];

async function process(item: string): Promise<string> {
  // async work
  return item;
}

export async function processAll(items: string[]): Promise<string[]> {
  collected.length = 0;
  for (const item of items) {
    // not awaited and not tracked
    process(item).then((r) => collected.push(r));
  }
  // returns before any push() has run
  return collected;
}
