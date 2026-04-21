// auth-gateway HTTP server
import express from "express";
import jwt from "jsonwebtoken";
import fetch from "node-fetch";
import { adminRoutes } from "./routes/admin.js";

// SEED: F003 (scan-07 crypto) — TLS verification disabled globally via env
// This is ALSO declared in fraud-scoring's .env.production; the scanner
// should see both env-file instances AND this process.env assignment.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

const app = express();
app.use(express.json());
app.use("/admin", adminRoutes);

// Outbound call to upstream — no retry / rate limit, hardcoded URL
async function forwardToFraudScoring(body: unknown) {
  const upstream = process.env.API_UPSTREAM ?? "https://fraud-scoring.internal:8000";
  // SEED: F020 (scan-04 PII flow) — outbound egress with user-controlled body; response echoed back
  const res = await fetch(`${upstream}/predict`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

app.post("/score", async (req, res) => {
  const result = await forwardToFraudScoring(req.body);
  res.json(result);
});

app.listen(3000, () => console.log("auth-gateway listening on :3000"));
