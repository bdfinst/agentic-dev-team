import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Session policy (security spec SEC-7):
//   - an idle session expires after 15 minutes without activity
//   - any session expires 12 hours after sign-in, active or not
const IDLE_TIMEOUT_MS = 15 * 60 * 1000;
const ABSOLUTE_TIMEOUT_MS = 12 * 60 * 60 * 1000;

interface Session {
  readonly signedInAt: number;
  readonly lastActivityAt: number;
}

function isExpired(session: Session, now: number = Date.now()): boolean {
  if (now - session.lastActivityAt >= IDLE_TIMEOUT_MS) return true;
  return now - session.signedInAt >= ABSOLUTE_TIMEOUT_MS;
}

function touch(session: Session, now: number = Date.now()): Session {
  if (isExpired(session, now)) {
    throw new Error("Cannot extend an expired session");
  }
  return { ...session, lastActivityAt: now };
}

const SIGN_IN = Date.UTC(2026, 2, 10, 9, 0, 0); // 2026-03-10 09:00:00 UTC

describe("session expiry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(SIGN_IN);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const freshSession = (): Session => ({
    signedInAt: Date.now(),
    lastActivityAt: Date.now(),
  });

  it("keeps a session alive one millisecond before the idle timeout", () => {
    const session = freshSession();

    vi.advanceTimersByTime(IDLE_TIMEOUT_MS - 1);

    expect(isExpired(session)).toBe(false);
  });

  it("expires a session exactly at the idle timeout", () => {
    const session = freshSession();

    vi.advanceTimersByTime(IDLE_TIMEOUT_MS);

    expect(isExpired(session)).toBe(true);
  });

  it("moves the idle deadline forward on activity", () => {
    const session = freshSession();
    vi.advanceTimersByTime(IDLE_TIMEOUT_MS - 1);

    const touched = touch(session);
    vi.advanceTimersByTime(IDLE_TIMEOUT_MS - 1);

    expect(touched.lastActivityAt).toBe(SIGN_IN + IDLE_TIMEOUT_MS - 1);
    expect(isExpired(touched)).toBe(false);
  });

  it("expires an active session at the absolute timeout", () => {
    let session = freshSession();
    const activityStep = IDLE_TIMEOUT_MS - 1;
    while (Date.now() + activityStep < SIGN_IN + ABSOLUTE_TIMEOUT_MS) {
      vi.advanceTimersByTime(activityStep);
      session = touch(session);
    }

    vi.setSystemTime(SIGN_IN + ABSOLUTE_TIMEOUT_MS);

    expect(isExpired(session)).toBe(true);
  });

  it("refuses to extend an expired session", () => {
    const session = freshSession();
    vi.advanceTimersByTime(IDLE_TIMEOUT_MS);

    expect(() => touch(session)).toThrow("Cannot extend an expired session");
  });
});
