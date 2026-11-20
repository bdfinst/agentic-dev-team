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
- **mutmut gives reach only:** `mutants/mutmut-stats.json` names the tests that reach each function, never the test that killed a mutant. Both tests reaching the symbol's function gives `coverage-backed` at `medium` confidence at most, with the basis stating function-level reach. Never report `mutation-backed` from mutmut. Tests that reach different functions give `coverage disagrees`.
- **No usable evidence** for a repo (nothing given, or `missing`, `unrecognised format`, `malformed: <parser error>`, `no contexts`): `static-judgment` with that reason.
- **Evidence for one of two repos:** the other repo's findings are `static-judgment: missing`, and Scope names which repos had evidence.

Accepted inputs (v1): coverage.py JSON written with `--show-contexts`; per-test Cobertura XML directory; per-test JaCoCo XML directory; per-test Istanbul JSON directory; per-test lcov directory; per-test raw V8 JSON directory; Stryker `mutation-report.json`; mutmut `mutants/mutmut-stats.json`. Go (coverprofile) coverage is `static-judgment` in v1 (#2343).

### Per-test JS capture

Run each test (or test file) alone and keep one report per test id in one directory, passed as `--coverage <repo>=<dir>`. A single aggregate file (`coverage-final.json`, `lcov.info`) has no per-test data and is `no contexts`.

- **Istanbul JSON:** `nyc --reporter=json --report-dir=cov-per-test/<id> <runner>`, then copy each `coverage-final.json` to `cov-per-test/<id>.json`. Jest: `jest <file> --coverage --coverageReporters=json --coverageDirectory=cov/<id>`.
- **lcov:** same runs with `--reporter=lcovonly` / `--coverageReporters=lcovonly`; keep each `lcov.info` as `<id>.info`.
- **Raw V8:** `NODE_V8_COVERAGE=v8-per-test/<id> node --test <file>`, then keep one JSON per id.

Every report in the directory must be the same format. A directory where no statement or line has a hit is `no contexts`.

### Per-test JaCoCo capture (Java)

JaCoCo writes one report per JVM run, so capture one run per test id and keep each report as its own file in one directory (for example `jacoco-per-test/<test-id>.xml`).

1. Run each test (or test class) alone with the agent: `-javaagent:jacocoagent.jar=destfile=target/jacoco/<test-id>.exec`. With Maven Surefire, run `mvn test -Dtest='<Class>#<method>' -Djacoco.destFile=target/jacoco/<test-id>.exec`.
2. Convert each `.exec` to XML: `java -jar jacococli.jar report target/jacoco/<test-id>.exec --classfiles target/classes --sourcefiles src/main/java --xml jacoco-per-test/<test-id>.xml`.
3. Pass the directory: `--coverage <repo>=jacoco-per-test`.

The file name is the test id. A line is covered when its `<line>` element has `ci` greater than 0. One malformed report makes the whole directory `malformed: <error>` and the repo falls back to `static-judgment`.

## Confidence

Same inputs, expected value, and assertion text: high. Same behavior name and expected value: medium. Name only: low. Static-only findings are capped at `suggestion` and carry `candidate; confirm with coverage before trimming`.

## Output line

```
[evidence: <coverage-backed|mutation-backed|coverage disagrees|mutation disagrees|static-judgment>; evidence-confidence: <high|medium|low>; basis: <text>] <Smell> | <test A> + <test B> | <action>
```

Group *Cross-Layer Overlap* under `Layer overlap (trim, not remove)` and the rest under `Layer misplacement`. Cite every finding with a path and line or a test name. Never report counts, coverage figures, or durations that were not measured. For an E2E, name the replacement tests and the double validation required before removal.
