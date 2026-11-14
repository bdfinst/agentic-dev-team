export function startSession(userId: string) {
  return { status: 200, cookie: `sid=${userId}.${Date.now()}; HttpOnly; Secure` };
}
