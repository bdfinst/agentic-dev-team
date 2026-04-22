import { z } from "zod";

export const UserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  createdAt: z.date(),
});

export type User = z.infer<typeof UserSchema>;

export function makeUser(email: string): Omit<User, "id" | "createdAt"> {
  return { email };
}

export * from "./errors.js";
