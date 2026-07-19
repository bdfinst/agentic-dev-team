// A batch processor starts each async task without awaiting and pushes results
// into shared state; tasks complete out of order and the done callback fires
// before the in-flight tasks finish, so results are dropped.
const results: string[] = [];

async function process(item: string): Promise<string> {
  // async work
  return item;
}

export function runBatch(items: string[], onDone: (r: string[]) => void): void {
  for (const item of items) {
    // BUG: not awaited and not tracked — the loop completes and onDone fires
    // with a partially-filled results array while tasks are still running.
    process(item).then((r) => results.push(r));
  }
  onDone(results);
}
