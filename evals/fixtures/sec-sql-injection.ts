import { Pool } from "pg";
import express, { Request, Response } from "express";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const app = express();
app.use(express.json());

// ISSUE: SQL injection via string concatenation
app.get("/api/users", async (req: Request, res: Response) => {
  const sortBy = req.query.sort || "name";
  const query = "SELECT id, name, email FROM users ORDER BY " + sortBy;
  const result = await pool.query(query);
  res.json(result.rows);
});

// ISSUE: SQL injection via template literal with user input
app.get("/api/users/search", async (req: Request, res: Response) => {
  const name = req.query.name as string;
  const query = `SELECT id, name, email FROM users WHERE name LIKE '%${name}%'`;
  const result = await pool.query(query);
  res.json(result.rows);
});

// ISSUE: SQL injection in login - classic auth bypass
app.post("/api/login", async (req: Request, res: Response) => {
  const { username, password } = req.body;
  const query =
    "SELECT * FROM users WHERE username = '" +
    username +
    "' AND password = '" +
    password +
    "'";
  const result = await pool.query(query);

  if (result.rows.length > 0) {
    res.json({ authenticated: true, user: result.rows[0] });
  } else {
    res.status(401).json({ authenticated: false });
  }
});

// ISSUE: SQL injection in DELETE with unvalidated ID
app.delete("/api/users/:id", async (req: Request, res: Response) => {
  const id = req.params.id;
  await pool.query("DELETE FROM users WHERE id = " + id);
  res.json({ deleted: true });
});

export default app;
