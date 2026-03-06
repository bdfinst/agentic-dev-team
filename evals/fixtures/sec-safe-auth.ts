import bcrypt from "bcrypt";
import { Pool } from "pg";
import { z } from "zod";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const SALT_ROUNDS = 12;

const RegisterSchema = z.object({
  email: z.string().email().max(255),
  password: z.string().min(8).max(128),
  name: z.string().min(1).max(100).regex(/^[a-zA-Z\s'-]+$/),
});

const LoginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export async function registerUser(input: unknown): Promise<{ id: string }> {
  const { email, password, name } = RegisterSchema.parse(input);

  const hashedPassword = await bcrypt.hash(password, SALT_ROUNDS);

  const result = await pool.query(
    "INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3) RETURNING id",
    [email, hashedPassword, name]
  );

  return { id: result.rows[0].id };
}

export async function authenticateUser(
  input: unknown
): Promise<{ id: string; email: string } | null> {
  const { email, password } = LoginSchema.parse(input);

  const result = await pool.query(
    "SELECT id, email, password_hash FROM users WHERE email = $1",
    [email]
  );

  if (result.rows.length === 0) {
    // Constant-time comparison even on missing user to prevent timing attacks
    await bcrypt.hash(password, SALT_ROUNDS);
    return null;
  }

  const user = result.rows[0];
  const isValid = await bcrypt.compare(password, user.password_hash);

  if (!isValid) {
    return null;
  }

  return { id: user.id, email: user.email };
}

export async function changePassword(
  userId: string,
  currentPassword: string,
  newPassword: string
): Promise<boolean> {
  const parsed = z.string().min(8).max(128).safeParse(newPassword);
  if (!parsed.success) return false;

  const result = await pool.query(
    "SELECT password_hash FROM users WHERE id = $1",
    [userId]
  );

  if (result.rows.length === 0) return false;

  const isValid = await bcrypt.compare(currentPassword, result.rows[0].password_hash);
  if (!isValid) return false;

  const newHash = await bcrypt.hash(newPassword, SALT_ROUNDS);
  await pool.query("UPDATE users SET password_hash = $1 WHERE id = $2", [
    newHash,
    userId,
  ]);

  return true;
}
