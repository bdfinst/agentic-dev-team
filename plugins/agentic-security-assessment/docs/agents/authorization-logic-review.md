# authorization-logic-review — rationale and provenance

## Why top-down

Complements `deep-code-reasoning` (which reasons bottom-up from suspicious
code to vulnerabilities) with a top-down approach: identify what the
application's authorization model is *supposed to do*, then check whether
the implementation actually does it everywhere.

The most common authorization failures are not "no auth at all" (Semgrep
catches those) but "auth enforced at the front door, not at the back
rooms" — controller-layer checks missing at the service or data-access
layer, or tenancy filters applied inconsistently across queries.

## Minimum two-location evidence rule

Authorization bugs are often structural — they arise from a consistent
policy that is not consistently enforced. Reporting single suspicious
lines is noise. The rule: report the gap between stated policy and
observed implementation — at least one location for the policy
declaration and at least one for the gap.
