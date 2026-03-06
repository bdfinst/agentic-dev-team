import { db } from "./database";
import { Result, ok, err } from "./result";

// --- Types ---

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  createdAt: Date;
}

interface UserResponse {
  id: string;
  name: string;
  email: string;
  role: string;
  createdAt: string;
}

// // Old user search implementation - keeping for rollback
// async function searchUsersLegacy(query: string) {
//   const users = await db.user.findMany({
//     where: { name: { contains: query } },
//   });
//   return users.map(u => ({
//     id: u.id,
//     name: u.name,
//     email: u.email,
//   }));
// }

// --- Admin user list ---

async function getAdminUsers(): Promise<Result<UserResponse[], string>> {
  const users = await db.user.findMany({
    where: { role: "admin" },
    orderBy: { createdAt: "desc" },
  });

  const response: UserResponse[] = [];
  for (const user of users) {
    response.push({
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      createdAt: user.createdAt.toISOString(),
    });
  }

  return ok(response);
}

// --- Manager user list ---

async function getManagerUsers(): Promise<Result<UserResponse[], string>> {
  const users = await db.user.findMany({
    where: { role: "manager" },
    orderBy: { createdAt: "desc" },
  });

  const response: UserResponse[] = [];
  for (const user of users) {
    response.push({
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      createdAt: user.createdAt.toISOString(),
    });
  }

  return ok(response);
}

// --- Regular user list ---

async function getRegularUsers(): Promise<Result<UserResponse[], string>> {
  const users = await db.user.findMany({
    where: { role: "user" },
    orderBy: { createdAt: "desc" },
  });

  const response: UserResponse[] = [];
  for (const user of users) {
    response.push({
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      createdAt: user.createdAt.toISOString(),
    });
  }

  return ok(response);
}

// --- Admin user creation ---

async function createAdminUser(
  name: string,
  email: string
): Promise<Result<UserResponse, string>> {
  const existing = await db.user.findUnique({ where: { email } });
  if (existing) {
    return err("Email already in use");
  }

  const trimmedName = name.trim();
  if (trimmedName.length === 0) {
    return err("Name must not be empty");
  }
  if (trimmedName.length > 100) {
    return err("Name must be under 100 characters");
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return err("Invalid email format");
  }

  const user = await db.user.create({
    data: { name: trimmedName, email, role: "admin" },
  });

  return ok({
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    createdAt: user.createdAt.toISOString(),
  });
}

// --- Manager user creation ---

async function createManagerUser(
  name: string,
  email: string
): Promise<Result<UserResponse, string>> {
  const existing = await db.user.findUnique({ where: { email } });
  if (existing) {
    return err("Email already in use");
  }

  const trimmedName = name.trim();
  if (trimmedName.length === 0) {
    return err("Name must not be empty");
  }
  if (trimmedName.length > 100) {
    return err("Name must be under 100 characters");
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return err("Invalid email format");
  }

  const user = await db.user.create({
    data: { name: trimmedName, email, role: "manager" },
  });

  return ok({
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    createdAt: user.createdAt.toISOString(),
  });
}

// --- Regular user creation ---

async function createRegularUser(
  name: string,
  email: string
): Promise<Result<UserResponse, string>> {
  const existing = await db.user.findUnique({ where: { email } });
  if (existing) {
    return err("Email already in use");
  }

  const trimmedName = name.trim();
  if (trimmedName.length === 0) {
    return err("Name must not be empty");
  }
  if (trimmedName.length > 100) {
    return err("Name must be under 100 characters");
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return err("Invalid email format");
  }

  const user = await db.user.create({
    data: { name: trimmedName, email, role: "user" },
  });

  return ok({
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    createdAt: user.createdAt.toISOString(),
  });
}

// --- Admin user deletion ---

async function deleteAdminUser(id: string): Promise<Result<void, string>> {
  const user = await db.user.findUnique({ where: { id } });
  if (!user) {
    return err("User not found");
  }
  if (user.role !== "admin") {
    return err("User is not an admin");
  }

  const adminCount = await db.user.count({ where: { role: "admin" } });
  if (adminCount <= 1) {
    return err("Cannot delete the last admin user");
  }

  await db.user.delete({ where: { id } });
  return ok(undefined);
}

// --- Manager user deletion ---

async function deleteManagerUser(id: string): Promise<Result<void, string>> {
  const user = await db.user.findUnique({ where: { id } });
  if (!user) {
    return err("User not found");
  }
  if (user.role !== "manager") {
    return err("User is not a manager");
  }

  await db.user.delete({ where: { id } });
  return ok(undefined);
}

// --- Regular user deletion ---

async function deleteRegularUser(id: string): Promise<Result<void, string>> {
  const user = await db.user.findUnique({ where: { id } });
  if (!user) {
    return err("User not found");
  }
  if (user.role !== "user") {
    return err("User is not a regular user");
  }

  await db.user.delete({ where: { id } });
  return ok(undefined);
}

export {
  getAdminUsers,
  getManagerUsers,
  getRegularUsers,
  createAdminUser,
  createManagerUser,
  createRegularUser,
  deleteAdminUser,
  deleteManagerUser,
  deleteRegularUser,
};
