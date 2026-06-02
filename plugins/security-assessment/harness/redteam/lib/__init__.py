"""Shared libraries for the red-team harness.

Modules:
    http_client      rate-limited, budget-tracked, audit-logged HTTP
    result_store     inter-script data passing (load / save JSON by name)
    scoring          extract_score + build_baseline_payload
    feature_dict     curated fraud-detection feature dictionary
    scope_check      CIDR allowlist + self-cert artifact hashing

Invariants (enforced by design):
    - All HTTP goes through http_client. The rate limiter, retries, budget,
      and audit logging live there. Scripts that import `requests` or
      `httpx` directly break the safety model.
    - All inter-script data goes through result_store. Scripts do not read
      each other's JSON files directly.
    - Budget is global. QueryBudgetExhausted is raised by http_client, not
      any one script.
"""
