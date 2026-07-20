// A mutex-style lock is released BEFORE the async write it was protecting has
// completed, because that write is never awaited. `writeRecord` returns a
// pending promise; control falls straight through to the `finally`, which calls
// `release()` while the write is still in flight. Another holder can then
// acquire the lock and interleave its own write with this unfinished, now
// unprotected one — the exact interleaving the lock existed to prevent.
interface Lock {
  release(): void;
}

async function writeRecord(data: string): Promise<void> {
  // async write to shared storage — completes on a later tick
}

export async function guardedWrite(lock: Lock, data: string): Promise<void> {
  try {
    // BUG: no `await`. writeRecord(data) starts the write and immediately
    // returns a pending promise that is discarded. The try block "completes"
    // synchronously even though the write has NOT finished.
    writeRecord(data);
  } finally {
    // BUG: release() fires while the write above is still pending, so the lock
    // stops guarding the write before the write is done. The correct code would
    // `await writeRecord(data)` inside the try so the lock is held for the whole
    // write.
    lock.release();
  }
}
