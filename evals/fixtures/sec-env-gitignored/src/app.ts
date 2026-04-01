import express from "express";

// Secrets loaded from environment variables (correct pattern)
const pat = process.env.AZURE_DEVOPS_EXT_PAT;
const bbToken = process.env.BITBUCKET_ACCESS_TOKEN;
const dbUrl = process.env.DATABASE_URL;

const app = express();

app.get("/api/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});
