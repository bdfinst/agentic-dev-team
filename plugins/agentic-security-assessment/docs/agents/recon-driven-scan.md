# recon-driven-scan — rationale and provenance

## Why this phase exists

Empirically validated on the NextGen portfolio. 12 repos scored zero
findings from Phase 1 SAST despite RECON narratives identifying concrete
risks. The targeted scan produced 75 confirmed findings (8 CRITICAL,
17 HIGH) including 2 production SQL injections, 1 RCE shape, an inverted-
boolean TLS-bypass library, hardcoded cross-environment credentials, and
a 12+-repo cross-repo credential reuse chain — all invisible to pattern-
only static analysis.

## Validation history (2026-05-01 NextGen rerun)

- **75 new findings** across 12 repos (mean 6.25/repo)
- **8 CRITICAL, 17 HIGH** added to portfolio severity counts
- **0 false alarms** — every finding had concrete file:line evidence
  matching a RECON claim
- All 12 repos promoted out of `00-no-findings.md`

Notable findings the original SAST missed:

- `search-service` — 2 production SQL injections in
  `PartialSearchByCreditAccount` and `PartialSearchByDebitAccount` (LIKE
  concat)
- `shared-tokenservice` — SQL injection in error-logging path; hardcoded
  `GenericTokenKey` across QA/UAT/Prod
- `profile-custompipes` — Flee + Dynamic LINQ RCE shape running in-
  process inside `profile-service`
- `notificationinfrastructure` — inverted-boolean TLS bypass library-
  amplified across all consumer Lambdas
- `Jupiter2020$` cross-repo credential reuse in 6 of 12 reruns (now
  confirmed in 12+ repos portfolio-wide)

## Why this is not deep-code-reasoning

`deep-code-reasoning` works bottom-up from suspicious code shapes;
`recon-driven-scan` works top-down from RECON's risk narrative. The two
are complementary — bottom-up finds shapes static rules miss because they
are novel; top-down finds shapes static rules miss because they require
domain context (which is in RECON, not in the source).

## Anti-fabrication rule

RECON itself can be wrong. A clean repo is a valid outcome. Emitting `[]`
when the RECON narrative is empty/generic or when none of its claims have
concrete code evidence is the correct behavior — never fabricate findings
to fill the array.
