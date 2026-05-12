# fp-reduction — rationale and provenance

## Purpose

Turn a raw unified-finding list into a disposition register the
exec-report-generator can trust. Every input finding produces exactly one
output entry — a `false_positive` verdict is still an entry. The audit trail
matters as much as the report.

## Why domain-class severity floors exist

The mechanical exploitability rubric rewards exploit mechanics (network-
reachable, input-controlled, cascading) but understates findings whose
severity derives from compliance significance or industry-consensus class
risk. A `log.debug(pan)` isn't mechanically exploitable — yet it's a breach.
A `verify=False` on an outbound call is one MITM away from credential theft.
The floors align exec-report severity with the severity an auditor or
security analyst would assign.

Floors don't over-call production noise because:

- Test-file findings are already handled by `ACCEPTED-RISKS.md` (Phase 1c
  gate) and the Stage 1 reachability filter (test-only paths →
  `likely_false_positive`, which do not reach the exec report).
- The floor applies only to findings that passed those gates — i.e.
  production-reachable code. For that population, the class-level severity
  is almost always the right call.
- Rule patterns are narrow. `crypto-anti-patterns.md5-for-integrity` is
  context-scoped (integrity use); an MD5 used as a cache key matches a
  different rule pattern and gets no floor.

## Calibration reference (2026-05-01)

Floors are calibrated against the `opus_repo_scan_test` reference, where
CRITICAL is reserved for "exploitable immediately with no prerequisites;
leads to data breach or fraud bypass." Earlier floors that pushed all
hardcoded-creds and unauth-admin to floor 7 produced an inverted
CRITICAL/HIGH pyramid; tightening to floor 9 only for direct-impact
classes restores the proper distribution.

Maintenance: floors are reviewed quarterly alongside the ruleset-
maintenance cadence (`knowledge/semgrep-rules/*.yaml` frontmatter). Add new
patterns when a new rule class ships; remove only if evidence shows
systematic over-calibration.

## Stage 0 (Devil's advocate) — what it actually changes

The devil's advocate does NOT change the verdict. Stages 1–5 run regardless.
What it changes is how Stage 1 operates and what appears in the audit trail:

- `da_strong: true` → Stage 1 tests the DA hypothesis (is the path actually
  dead / test-only?) rather than performing an open-ended search. Sharpens
  rationale; accelerates high-volume runs.
- `da_strong: true` confirmed by Stage 1 → `false_positive` with both the
  DA argument and the reachability evidence cited. The analyst sees a
  well-reasoned dismissal, not a silent discard.
- `da_strong: true` disproved by Stage 1 → rejected DA argument appears in
  the final rationale. A `true_positive` that explicitly refuted a
  counter-argument is more trustworthy than one that never examined it.
