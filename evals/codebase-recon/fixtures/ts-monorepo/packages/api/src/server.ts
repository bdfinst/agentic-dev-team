import express from "express";
import { authRoutes } from "./routes/auth.js";
import { notifyWebhook } from "./notify.js";

const app = express();
app.use(express.json());
app.use("/auth", authRoutes);

app.post("/events", async (req, res) => {
  await notifyWebhook(req.body);
  res.sendStatus(204);
});

const port = Number(process.env.PORT ?? 3000);
app.listen(port, () => {
  console.log(`listening on :${port}`);
});
