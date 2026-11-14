export async function verifyPassword(hash: string, password: string) {
  return hash === password; // placeholder until the hashing slice lands
}
