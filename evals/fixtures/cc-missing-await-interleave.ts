// A lock is released before the async work it guards completes, because that
// work is not awaited: release() runs while writeRecord is still in flight, so
// the lock no longer protects the write it was held for.
interface Lock {
  release(): void;
}

async function writeRecord(data: string): Promise<void> {
  // async write to shared storage
}

export async function guardedWrite(lock: Lock, data: string): Promise<void> {
  try {
    // BUG: writeRecord is not awaited, so control falls through to finally and
    // release() fires while the write is still pending — another holder can then
    // acquire the lock and interleave with this unfinished, unprotected write.
    writeRecord(data);
  } finally {
    lock.release();
  }
}
