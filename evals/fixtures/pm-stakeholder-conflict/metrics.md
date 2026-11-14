# Data pulled by analytics (last 90 days)

## Partial-refund bug
- Partial refunds issued: 1,180
- Over-refunded amount written off: $41,300 (about $13,800/month)
- Support tickets caused by refund mismatches: 260
- Trend: partial refunds up 22% quarter over quarter

## Bulk discount prospects
- Prospect 1 (Northwind-like retailer, $60k ARR): sales stage "evaluation";
  procurement call notes say "discount codes nice to have; security review is
  the blocker".
- Prospect 2 ($30k ARR): stage "negotiation"; notes say "needs bulk codes for
  launch event on the 28th of next month".
- Workaround available today: support can create codes one at a time
  (about 2 minutes per code; prospect 2 needs about 150 codes).

## Engineering estimates
- Partial-refund fix: 3 days, plus 2 days to reconcile historic data.
- Bulk discount codes: 8 days (the full sprint).
