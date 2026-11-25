// Control: ESM imports, const, spread copies, and non-mutating array methods.
import { readFile } from "node:fs/promises";
import path from "node:path";

const base = import.meta.dirname;
let seen = 0;

const total = (items) => items.reduce((sum, item) => sum + item, 0);
const sorted = (items) => [...items].sort((a, b) => a - b);
const newest = (items) => items.toSorted((a, b) => b - a);
const reversed = (items) => items.toReversed();
const withName = (user, name) => ({ ...user, name });

function countAll(list) {
  for (let i = 0; i < list.length; i++) {
    seen = seen + 1;
  }
  return seen;
}

export const load = (name) => readFile(path.join(base, name), "utf8");
export { total, sorted, newest, reversed, withName, countAll };
