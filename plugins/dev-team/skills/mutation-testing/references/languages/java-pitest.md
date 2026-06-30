# Mutation Testing — Java / Kotlin (pitest)

Tool: [pitest](https://pitest.org/). Detection: `pom.xml` or `build.gradle` has `pitest` plugin.

## Install / detect

Maven:

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.4</version>
</plugin>
```

Gradle: add the `info.solidsoft.pitest` plugin.

## Run (scoped)

```bash
# Specific class
mvn pitest:mutationCoverage -DtargetClasses="com.example.Calculator"

# With history (faster incremental runs)
mvn pitest:mutationCoverage -DwithHistory
```

## Per-mutant timeout flag

CLI:

```bash
mvn pitest:mutationCoverage -DtimeoutConst=60 -DtimeoutFactor=2.5
```

Default shipped: 60 s constant. Set `-DtimeoutConst` to `timeout_seconds` (formula in [`SKILL.md`](../../SKILL.md) Step 1b).

## Native report → schema mapping

Source: `target/pit-reports/<date>/mutations.xml`. Map `<mutation status="SURVIVED">` to `survived`; `<mutation status="NO_COVERAGE">` to `survived` (uncovered, but technically a survivor for downstream callers).

```json
{
  "schema_version": 1,
  "tool": "pitest",
  "scope": ["src/main/java/com/example/Calculator.java"],
  "captured_at": "2026-06-19T14:25:11Z",
  "total": 36,
  "killed": 30,
  "survived": 4,
  "equivalent": 2,
  "survivors": [
    { "file": "src/main/java/com/example/Calculator.java", "line": 19, "operator": "CONDITIONALS_BOUNDARY", "status": "survived" }
  ]
}
```

## Language-specific notes

- **`withHistory`** — pitest skips mutants killed in prior runs when history is enabled. First run is slow; incremental runs are fast. Use it in CI for changed-file gates.
- The pitest HTML report under `target/pit-reports/` is the canonical triage view — note the path when reporting back.
- For multi-module Maven projects, run `pitest:mutationCoverage` from the aggregator POM and review each module's report individually.
