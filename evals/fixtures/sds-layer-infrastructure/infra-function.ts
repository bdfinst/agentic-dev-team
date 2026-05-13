// SKILL: semantic-duplication-scan
// EXPECTED layer: "infrastructure"
// REASON: imports pg (PostgreSQL client) — database coupling

import { Pool } from "pg";

const pool = new Pool();

async function getUserById(userId: string): Promise<Record<string, unknown>> {
  const result = await pool.query("SELECT * FROM users WHERE id = $1", [userId]);
  return result.rows[0];
}
