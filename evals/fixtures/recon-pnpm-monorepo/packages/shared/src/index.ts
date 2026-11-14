export interface User { id: string; email: string; hash: string }

const users: User[] = [];

export async function findUser(email: string): Promise<User | undefined> {
  return users.find((u) => u.email === email);
}
