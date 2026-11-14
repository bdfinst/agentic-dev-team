import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace("Bearer ", "");
  if (!token) {
    res.status(401).json({ data: null, error: "unauthorized", meta: {} });
    return;
  }
  try {
    jwt.verify(token, process.env.JWT_SECRET ?? "");
    next();
  } catch {
    res.status(401).json({ data: null, error: "unauthorized", meta: {} });
  }
}
