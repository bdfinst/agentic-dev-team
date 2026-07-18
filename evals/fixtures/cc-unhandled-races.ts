// Distinct concurrency hazards: a database read-modify-write with no
// transaction, a file read-modify-write with no lock, and an event handler
// mutating shared state across a non-atomic check-then-splice.

import { readFile, writeFile } from "fs/promises";

interface DB {
  query(sql: string, params: unknown[]): Promise<{ views: number }>;
}

// Read-modify-write with no transaction or optimistic lock: two concurrent
// increments both read the same `views` and one update is lost.
export async function incrementViews(db: DB, postId: string): Promise<void> {
  const row = await db.query("SELECT views FROM posts WHERE id = ?", [postId]);
  await db.query("UPDATE posts SET views = ? WHERE id = ?", [row.views + 1, postId]);
}

// Open-read-modify-write on a shared file with no lock: concurrent callers read
// the same contents and the last writer clobbers the others' appends.
export async function appendAudit(entry: string): Promise<void> {
  const existing = await readFile("audit.log", "utf8");
  await writeFile("audit.log", existing + entry + "\n");
}

// Shared mutable state mutated from concurrent event callbacks with no guard:
// the length check and the splice are not atomic across interleaved events.
const pending: string[] = [];
export function onMessage(msg: string, flush: (items: string[]) => void): void {
  pending.push(msg);
  if (pending.length >= 100) {
    flush(pending.splice(0));
  }
}
