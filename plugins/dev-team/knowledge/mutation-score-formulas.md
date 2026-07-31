# Mutation score formulas

Canonical formulas for `mutation-kill` (the autonomous survivor-kill agent)
and the `/mutation-testing` skill (advisory scoring/reporting). Both compute
identical numbers from a mutation report's `Killed`/`Survived`/`Timeout`/
`NoCoverage` counts — this file is the single definition so the two never
drift on naming or arithmetic.

## Honest vs. reported score

Mutation tools count **timed-out** mutations as "killed." They are not — a
score inflated by timeouts is not evidence of good tests (observed: one run
scored 61.3% "killed," 76% of which were timeouts; targeted tests that let
those mutations *complete* instead of timing out dropped the honest score to
30.36%). This is a separate observed incident from the worked example in
`skills/mutation-testing/SKILL.md`'s Output format section (23.0% honest vs.
61.3% claimed, 999/1305 timeouts) — both are real, independently sourced
illustrations of the same failure mode, not one canonical figure restated
inconsistently.

```
honest_score   = Killed / (Killed + Survived + NoCoverage)
reported_score = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
```

Same formula, two fixed field names — not free-to-unify synonyms:
`mutation_report.py` emits the dataclass field `reported_score`;
`skills/mutation-testing/SKILL.md`'s `--emit-json` machine-readable output
key is `claimed_score` (a stable, versioned schema — see that file's
Machine-readable output section). Both name what the mutation tool's own
report/HTML prints. **`honest_score` is the only number that gates a round
or a file** — Timeout stays out of the numerator. Report both, so a reviewer
comparing them sees an honest gap (numerator delta) rather than a formula
mismatch. `Timeout` and `NoCoverage` counts always print separately
alongside both scores.

## Raw vs. adjusted score (accepted survivors)

When one or more survivors are marked `status: "accepted"` (a real, killable
mutant deliberately deferred this pass — distinct from `"equivalent"`), also
print:

```
raw_score      = honest_score (unchanged)
adjusted_score = Killed / (Killed + (Survived - Accepted) + NoCoverage)
```

Label both clearly (e.g. `Raw: 68.57% (24/35) · Adjusted for 11 accepted
survivors: 100% (24/24)`), plus a per-mutant "Accepted Survivors (deferred)"
table (file, line, operator, reason). Never let `adjusted_score` stand
alone — `raw_score` plus the reason table is what keeps a documented
deferral from silently vanishing.

## NoCoverage is a first-class signal

Each `NoCoverage → Killed` conversion improves the score as much as killing
a `Survived` mutant — and NoCoverage paths are usually easier, because
**any** test that reaches the line kills the mutant (no specific-value
assertion required). Prioritize NoCoverage coverage before attacking hard
Survived mutations.
