import { db } from "./db";

export interface Account {
  id: string;
  email: string;
  status: "active" | "suspended" | "closed";
  createdAt: Date;
}

export class AccountNotFoundError extends Error {
  constructor(readonly accountId: string) {
    super(`Account ${accountId} not found`);
    this.name = "AccountNotFoundError";
  }
}

/**
 * Normalizes an email address for lookups: trims surrounding whitespace and
 * lower-cases the whole address.
 *
 * @param email - The address as the user typed it.
 * @returns The normalized address.
 */
export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

/**
 * Finds an account by its email address.
 *
 * @param email - The address to look up; it is normalized first.
 * @returns The matching account, or `null` when no account uses the address.
 */
export async function findAccountByEmail(
  email: string,
): Promise<Account | null> {
  const row = await db.accounts.findFirst({
    where: { email: normalizeEmail(email) },
  });
  return row ?? null;
}

/**
 * Loads an account by its id.
 *
 * @param accountId - The account's primary key.
 * @returns The matching account, or `null` when no account has that id.
 */
export async function getAccount(accountId: string): Promise<Account> {
  const row = await db.accounts.findUnique({ where: { id: accountId } });
  if (!row) {
    throw new AccountNotFoundError(accountId);
  }
  return row;
}

/**
 * Lists the accounts in a given status, newest first.
 *
 * @param status - Only accounts in this status are returned.
 * @param limit - The maximum number of accounts to return.
 * @returns Up to `limit` accounts, ordered by `createdAt` descending.
 */
export async function listAccountsByStatus(
  status: Account["status"],
  limit: number,
): Promise<Account[]> {
  return db.accounts.findMany({
    where: { status },
    orderBy: { createdAt: "desc" },
    take: limit,
  });
}

/**
 * Suspends an active account. Suspending an account that is already
 * suspended or closed leaves it unchanged.
 *
 * @param accountId - The account to suspend.
 * @returns The account after the change.
 */
export async function suspendAccount(accountId: string): Promise<Account> {
  const account = await getAccount(accountId);
  if (account.status !== "active") {
    return account;
  }
  return db.accounts.update({
    where: { id: accountId },
    data: { status: "suspended" },
  });
}
