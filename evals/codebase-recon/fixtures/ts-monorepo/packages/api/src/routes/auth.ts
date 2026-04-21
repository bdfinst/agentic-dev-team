import { Router } from "express";
import jwt from "jsonwebtoken";

export const authRoutes = Router();

authRoutes.post("/login", (req, res) => {
  const { email } = req.body;
  const secret = process.env.JWT_SECRET;
  if (!secret) {
    res.status(500).json({ error: "server misconfigured" });
    return;
  }
  const token = jwt.sign({ sub: email }, secret, { expiresIn: "1h" });
  res.json({ token });
});

authRoutes.post("/verify", (req, res) => {
  const { token } = req.body;
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET!);
    res.json({ valid: true, decoded });
  } catch {
    res.status(401).json({ valid: false });
  }
});
