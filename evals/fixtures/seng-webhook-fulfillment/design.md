# Design: PayGate webhook receiver

Status: proposed. No code written yet.

## Goal
Ship physical orders as soon as PayGate tells us a payment succeeded,
instead of polling PayGate every 10 minutes.

## Flow
1. PayGate sends `POST https://shop.example.com/webhooks/paygate` with JSON:
   `{"event_id": "...", "type": "payment.succeeded", "order_id": "...", "amount": 2599}`
2. The endpoint is public (PayGate calls from rotating cloud IPs, so we can't
   allowlist).
3. The handler parses the JSON, looks up `order_id`, and calls
   `fulfillment.ship(order_id)`, which creates a warehouse pick ticket and
   emails the customer a tracking link.
4. Respond `200 OK`.

## Details
- PayGate signs every webhook with an `X-PayGate-Signature` header
  (HMAC-SHA256 of the raw body with a per-merchant secret) and includes a
  `t=` timestamp in that header. We plan to parse JSON directly for now and
  "add signature checking later if needed".
- PayGate retries delivery on any non-2xx or timeout, up to 3 days, and may
  deliver the same event more than once.
- The per-merchant webhook secret will be stored in `config/paygate.yml`
  next to the API key, which is committed to the repo for simplicity.
- Handler logs the full request body and headers at INFO for debugging.
