import { Router } from "express";

export const accountsRouter = Router();

accountsRouter.get("/", (_req, res) => {
  res.json({ data: [], error: null, meta: {} });
});
