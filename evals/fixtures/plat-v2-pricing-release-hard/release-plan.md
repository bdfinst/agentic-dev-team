# Release plan: pricing v2

1. Merge to main; CI builds the image and runs the tests.
2. Canary takes 5% of traffic for 5 minutes. If the pods are healthy,
   CI runs the migration and promotes to 100%.
3. v2 pricing is behind the `pricing_v2_enabled` flag, so if anything goes
   wrong we flip the flag or redeploy the previous image. Rollback is safe.

Pricing serves every cart and checkout request (about 900 requests/s at peak).
The previous image reads `price_rules.legacy_discount_pct`.
