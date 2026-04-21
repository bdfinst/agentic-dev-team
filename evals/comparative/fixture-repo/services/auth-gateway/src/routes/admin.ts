// Admin routes — demonstrates several SEEDED auth findings
import { Router } from "express";
import jwt from "jsonwebtoken";

export const adminRoutes = Router();

// SEED: F021 (scan-02 auth) — admin endpoint with no auth middleware
adminRoutes.post("/flush-cache", (_req, res) => {
  // Dangerous operation; not gated.
  res.json({ flushed: true });
});

// SEED: F022 (scan-02 auth + scan-07) — JWT verified with hardcoded secret fallback
adminRoutes.post("/issue-token", (req, res) => {
  const secret = process.env.JWT_SECRET ?? "fallback-secret-for-dev";
  const token = jwt.sign({ sub: req.body.email, role: "admin" }, secret);
  res.json({ token });
});
