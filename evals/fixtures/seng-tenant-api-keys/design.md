# Design: Public reporting API for tenants

Status: proposed. No code written yet.

## Summary
Tenants (customer companies) get an API to pull their own reports.

## Authentication
- Each tenant admin can create API keys in Settings. A key is a random
  40-character string shown once.
- Keys are stored in the `api_keys` table in plaintext so support can look
  them up when a customer loses one.
- Requests send the key in the `X-Api-Key` header.

## Endpoints
- `GET /v1/reports?tenant_id=<id>&from=<date>&to=<date>`
- `GET /v1/reports/<report_id>/download`

## Authorization
- The gateway validates that `X-Api-Key` exists in `api_keys`.
- The handler then queries reports using the `tenant_id` from the query
  string. For `/download`, it fetches by `report_id` (sequential integer).

## Operations
- The gateway access log records the full request URL and all request
  headers; logs are shipped to a vendor log platform that all engineers and
  the support contractor can search.
- No per-key rate limit in v1.
