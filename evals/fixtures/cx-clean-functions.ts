// PASS: Short functions, low cyclomatic complexity, shallow nesting, few params

interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "member" | "guest";
}

function formatUserName(user: User): string {
  return `${user.name} (${user.role})`;
}

function isAdmin(user: User): boolean {
  return user.role === "admin";
}

function filterActiveUsers(users: User[], role?: string): User[] {
  if (!role) {
    return users;
  }
  return users.filter((u) => u.role === role);
}

function buildGreeting(name: string, timeOfDay: string): string {
  const prefix = timeOfDay === "morning" ? "Good morning" : "Hello";
  return `${prefix}, ${name}!`;
}

function calculateTotal(prices: number[]): number {
  return prices.reduce((sum, price) => sum + price, 0);
}

function clampValue(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
