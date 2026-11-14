export const MAX_FAILED_LOGINS = 5;

export interface Account {
  readonly id: string;
  readonly passwordHash: string;
  readonly failedLogins: number;
  readonly locked: boolean;
}

export type LoginResult =
  | { readonly ok: true; readonly sessionId: string; readonly account: Account }
  | {
      readonly ok: false;
      readonly reason: "locked" | "bad-password";
      readonly account: Account;
    };

export interface Hasher {
  matches(password: string, hash: string): boolean;
}

export function login(
  account: Account,
  password: string,
  hasher: Hasher,
  newSessionId: () => string,
): LoginResult {
  if (account.locked) {
    return { ok: false, reason: "locked", account };
  }
  if (hasher.matches(password, account.passwordHash)) {
    return {
      ok: true,
      sessionId: newSessionId(),
      account: { ...account, failedLogins: 0 },
    };
  }
  const failedLogins = account.failedLogins + 1;
  return {
    ok: false,
    reason: "bad-password",
    account: {
      ...account,
      failedLogins,
      locked: failedLogins >= MAX_FAILED_LOGINS,
    },
  };
}
