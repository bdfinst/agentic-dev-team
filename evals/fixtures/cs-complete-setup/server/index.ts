import express from "express";
import { accountsRouter } from "./routes/accounts";
import { requireAuth } from "./middleware/auth";

const app = express();
app.use(express.json());
app.use(express.static("dist/client"));
app.use("/api/accounts", requireAuth, accountsRouter);
app.get("/health", (_req, res) => {
  res.json({ data: "ok", error: null, meta: {} });
});
app.listen(4000);
