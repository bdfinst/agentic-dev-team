# Layer overlap

Find tests at different layers that assert the same behavior. The rule for which one wins (keep the unit test; the component test keeps only seam assertions) is in `knowledge/cd-test-architecture.md`, *Overlap resolution rule*. This reference covers pairing and evidence.

## Pairing

- Classify each test by its actual layer, not its name. A unit-named test does no real DB, network, or filesystem I/O; sociable unit tests with in-memory fakes are fine.
- Map each test to the production symbol it exercises, with CodeGraph (`codegraph_explore`) first and Grep/Read as the fallback.
- Pair tests by production symbol per module. Cap at 20 pairs per module; say when capped.
- Report *Cross-Layer Overlap* only when both layers are in scope. With one layer in scope, say so in one line and emit no overlap findings.

## Evidence

Per repo, from `--coverage` and `--mutation`. Detect the format with `scripts/coverage_evidence_detect.py`; it returns the format or the exact reason.

- **Shared lines:** at least one covered production line inside the paired symbol's body. Imports, fixtures, and boilerplate outside the body never count.
- **Coverage:** shared lines give `coverage-backed`. Disjoint lines give `coverage disagrees`: downgrade one confidence level and never report above `suggestion`.
- **Mutation:** both tests kill at least one common mutant inside the symbol's body gives `mutation-backed` (strongest; overrides coverage). No mutant killed by both inside the body (neither kills any, or they kill different ones) gives `mutation disagrees`, with the same downgrade.
- **No usable evidence** for a repo (nothing given, or `missing`, `unrecognised format`, `malformed: <parser error>`, `no contexts`): `static-judgment` with that reason.
- **Evidence for one of two repos:** the other repo's findings are `static-judgment: missing`, and Scope names which repos had evidence.

Accepted inputs (v1): coverage.py JSON written with `--show-contexts`; per-test Cobertura XML directory; per-test Istanbul JSON directory; Stryker `mutation-report.json`; mutmut stats JSON. Java (JaCoCo) and Go (coverprofile) coverage are `static-judgment` in v1 (#2342, #2343).

## Confidence

Same inputs, expected value, and assertion text: high. Same behavior name and expected value: medium. Name only: low. Static-only findings are capped at `suggestion` and carry `candidate; confirm with coverage before trimming`.

## Output line

```
[evidence: <coverage-backed|mutation-backed|static-judgment>; evidence-confidence: <high|medium|low>; basis: <text>] <Smell> | <test A> + <test B> | <action>
```

Group *Cross-Layer Overlap* under `Layer overlap (trim, not remove)` and the rest under `Layer misplacement`. Cite every finding with a path and line or a test name. Never report counts, coverage figures, or durations that were not measured. For an E2E, name the replacement tests and the double validation required before removal.
