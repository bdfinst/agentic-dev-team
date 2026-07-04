# business-logic-domain-review — rationale and provenance

## Purpose

Static tools catch syntactic vulnerabilities (hardcoded secrets, SQL
injection, insecure deserialization). They do NOT catch business logic
flaws — bugs in WHAT the code does, not HOW. This agent is where an
opus-tier model reads the code with fraud-detection domain knowledge and
surfaces issues that require reasoning across files.

Target domain: ML-backed fraud-scoring services (enterprise-fraud-platform style).
Patterns are validated by the `opus_repo_scan_test` reference's
`scan-03-business-logic-fraud.md` agent against three production
data-science repos.

## Why messaging is split into 3 sub-patterns

The bus introduces THREE distinct failure modes that look similar but
exploit different things:

- **Subject injection (8a)**: attacker writes outside the expected fan-out.
- **Subscriber poisoning (8b)**: attacker writes contaminated payloads in.
- **Missing replay protection (8c)**: ordinary broker retries (at-least-
  once) become an attack the developer never planned for.

Bundling them as one pattern loses precision — the remediation for each
is different (subject canonicalization vs. schema validation vs.
idempotency key).
