export type User = { id: string; email: string; passwordHash: string };
const users = new Map<string, User>();
export async function findByEmail(email: string) {
  return [...users.values()].find((u) => u.email === email);
}
