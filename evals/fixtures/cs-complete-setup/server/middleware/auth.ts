import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

const jwtSecret = process.env.JWT_SECRET;
if (!jwtSecret) {
  throw new Error("JWT_SECRET must be set");
}

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace("Bearer ", "");
  if (!token) {
    res.status(401).json({ data: null, error: "unauthorized", meta: {} });
    return;
  }
  try {
    jwt.verify(token, jwtSecret);
    next();
  } catch {
    res.status(401).json({ data: null, error: "unauthorized", meta: {} });
  }
}
