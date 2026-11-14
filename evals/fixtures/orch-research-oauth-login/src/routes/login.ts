import { verifyPassword } from "../users/passwords";
import { findByEmail } from "../users/store";
import { startSession } from "./session";

export async function login(req: { body: { email: string; password: string } }) {
  const user = await findByEmail(req.body.email);
  if (!user || !(await verifyPassword(user.passwordHash, req.body.password))) {
    return { status: 401 };
  }
  return startSession(user.id);
}
