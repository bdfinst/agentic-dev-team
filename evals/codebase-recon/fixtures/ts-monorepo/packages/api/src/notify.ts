import fetch from "node-fetch";

export async function notifyWebhook(payload: unknown): Promise<void> {
  const url = process.env.WEBHOOK_URL;
  if (!url) return;
  await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}
