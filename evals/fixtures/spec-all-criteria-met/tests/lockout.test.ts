import { describe, it, expect } from "vitest";
import { login, type Account, type Hasher } from "../src/lockout";

const hasher: Hasher = {
  matches: (password, hash) => `hashed:${password}` === hash,
};
const newSessionId = () => "session-1";

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: "a1",
    passwordHash: "hashed:secret",
    failedLogins: 0,
    locked: false,
    ...overrides,
  };
}

describe("login lockout", () => {
  it("returns a session for the correct password", () => {
    const result = login(account(), "secret", hasher, newSessionId);
    expect(result).toMatchObject({ ok: true, sessionId: "session-1" });
  });

  it("locks the account on the fifth consecutive wrong password", () => {
    const result = login(
      account({ failedLogins: 4 }),
      "wrong",
      hasher,
      newSessionId,
    );
    expect(result.ok).toBe(false);
    expect(result.account.locked).toBe(true);
  });

  it("does not lock the account after four wrong passwords", () => {
    const result = login(
      account({ failedLogins: 3 }),
      "wrong",
      hasher,
      newSessionId,
    );
    expect(result.account).toMatchObject({ failedLogins: 4, locked: false });
  });

  it("refuses the correct password on a locked account", () => {
    const result = login(
      account({ locked: true }),
      "secret",
      hasher,
      newSessionId,
    );
    expect(result).toMatchObject({ ok: false, reason: "locked" });
  });

  it("resets the failed-login count after a successful login", () => {
    const result = login(
      account({ failedLogins: 3 }),
      "secret",
      hasher,
      newSessionId,
    );
    expect(result.account.failedLogins).toBe(0);
  });
});
