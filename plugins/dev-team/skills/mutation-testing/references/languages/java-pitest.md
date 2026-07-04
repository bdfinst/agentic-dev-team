# Mutation Testing — Java / Kotlin (pitest)

Tool: [pitest](https://pitest.org/). Detection: `pom.xml` or `build.gradle` has `pitest` plugin.

## Install / detect

Both install paths are **project-scoped by design** — the Maven `<plugin>` declaration and the Gradle `info.solidsoft.pitest` plugin resolve through the build tool's own dependency resolution, not through any user-configured `PATH`. There is no meaningful "global" alternative to pitest, so this language avoids the silent-failure trap the skill's "prefer local install" note is guarding against.

Maven:

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <version>1.17.4</version>
</plugin>
```

Gradle: add the `info.solidsoft.pitest` plugin.

Confirm the plugin resolves before configuring a run:

```bash
# Maven: prints the help header for the mutationCoverage goal
./mvnw org.pitest:pitest-maven:help -Ddetail=true -Dgoal=mutationCoverage | head -1

# Gradle: lists the pitest tasks the plugin registers
./gradlew tasks --group=pitest
```

## Run (scoped)

> When capturing run output to a log file, do **not** use a bare `mvn pitest:mutationCoverage ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a tool failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

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
