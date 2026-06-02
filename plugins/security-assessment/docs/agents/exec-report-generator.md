# exec-report-generator — rationale and provenance

## Purpose

Transform the security-assessment pipeline's structured artifacts into a
publication-ready report suitable for CISO / CTO distribution. Match the
four-document output shape of the `opus_repo_scan_test` reference
(per-repo × N + cross-repo summary) with presentational severity that
business readers understand.

This is the final agent in the `/security-assessment` pipeline. It does not
detect, does not disposition, does not score — it synthesizes pure
narrative from the upstream artifacts.

## Why dedup + CWE + reachability invariants exist

Per the primitives contract v1.1.0 § "Severity mapping":

1. **Every CRITICAL or HIGH finding must have a CWE.** Without CWE, the
   finding cannot be triaged against a regulatory framework or industry
   priority list. Missing CWE → Appendix B (not silently dropped, not
   silently downgraded).
2. **Every CRITICAL or HIGH finding must have a reachability trace** (from
   the disposition register). Without reachability, the severity claim is
   speculative.
3. **Dedup applied.** One credential in N config variants is one Section 2
   / Section 3 entry with N locations in its "File:Line" field, not N
   entries. Treating identical findings as separate inflates apparent
   risk and dilutes priority signals.

These apply to CRITICAL and HIGH only. MEDIUM and LOW flow through
regardless.

## Why Section 0 is written last

The Top 3 Actions in Section 0 depend on what appears in Sections 2 and 5.
Writing Section 0 first leads to action lists that don't track the actual
findings — empirically a source of report rework.

## CWE format conventions (why three formats)

Three different CWE format conventions are deliberate:

- **Dashboard (Section 1, dense table):** number-only — readability of a
  dense grid suffers when names are inlined.
- **Detail blocks (Section 2):** full names — readers reach Section 2 for
  triage and need the human-readable context.
- **Inline (Section 3, condensed rows):** number-only — same density
  argument as the dashboard.

`+` vs `/` as separator: `+` reads as "and" (both CWE issues apply);
`/` reads as "or" (uncertain which CWE applies). The latter hides
ambiguity behind notation. Always use `+`.
