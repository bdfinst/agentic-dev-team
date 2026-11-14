# Checkout reliability, last 30 days

- Checkout availability 98.7% against a 99.9% target.
- 81% of failed checkouts were timeouts from `notify.send_confirmation_email`.
  The email provider behind `notify` has 1-3 s latency spikes several times a day.
- p99 checkout latency 2.4 s; p50 0.4 s.
- When notify times out, the customer sees an error but the order IS saved,
  so many retry and place duplicate orders.
- Inventory and pricing: 99.98% success, p99 under 150 ms.
