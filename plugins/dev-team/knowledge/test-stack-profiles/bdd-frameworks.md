# BDD Frameworks — per-language wire-in

The minimal steps to wire a BDD runner into a project, one section per supported
language. Use this **after** `../references/bdd-value-guide.md` recommends
`bdd-runner` mode — this file is the mechanics, not the decision.

Every runner here outputs JUnit-XML (or an equivalent the CI already understands),
so the BDD suite plugs into the existing pipeline without new reporting.

---

## JS/TS — Cucumber.js

- **Framework:** [@cucumber/cucumber](https://github.com/cucumber/cucumber-js) (v11+).
- **Install:** `npm install --save-dev @cucumber/cucumber`
- **Directory layout:**
  - `features/` — `.feature` files.
  - `features/support/` — step definitions and world/hooks.
- **Runner config** — `cucumber.yaml` (or `cucumber.js`) at repo root:
  ```yaml
  default:
    require:
      - features/support/**/*.js
    format:
      - "junit:reports/cucumber-junit.xml"
  ```
- **Step stub (pending):**
  ```js
  import { Given } from "@cucumber/cucumber";
  Given("a precondition", function () {
    return this.pending(); // marks the step (and scenario) pending
  });
  ```
- **Run:** `npx cucumber-js`
- **CI note:** the `junit` formatter writes `reports/cucumber-junit.xml`; point the existing JUnit reporter at it. Cucumber.js runs alongside Vitest/Jest — they are complementary, not alternatives.

---

## Java / Maven — Cucumber-JVM

- **Framework:** [Cucumber-JVM](https://github.com/cucumber/cucumber-jvm) on the JUnit 5 platform.
- **Install** — add to `pom.xml`:
  ```xml
  <dependency>
    <groupId>io.cucumber</groupId>
    <artifactId>cucumber-java</artifactId>
    <version>7.18.1</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>io.cucumber</groupId>
    <artifactId>cucumber-junit-platform-engine</artifactId>
    <version>7.18.1</version>
    <scope>test</scope>
  </dependency>
  ```
- **Directory layout:**
  - `src/test/resources/features/` — `.feature` files.
  - `src/test/java/.../steps/` — step-definition classes.
- **Runner config** — a suite entry point:
  ```java
  import org.junit.platform.suite.api.*;

  @Suite
  @IncludeEngines("cucumber")
  @SelectClasspathResource("features")
  public class RunCucumberTest {}
  ```
  (add `import static io.cucumber.junit.platform.engine.Constants.*;` only if you also set `@ConfigurationParameter` options such as the `pretty` plugin.)
- **Step stub (pending):**
  ```java
  import io.cucumber.java.en.Given;
  import io.cucumber.java.PendingException;

  public class Steps {
    @Given("a precondition")
    public void a_precondition() { throw new io.cucumber.java.PendingException(); }
  }
  ```
- **Run:** `mvn test` (Surefire discovers the JUnit 5 suite automatically).
- **CI note:** Surefire emits JUnit XML under `target/surefire-reports/` — no extra config.

---

## Java / Gradle — Cucumber-JVM

Same engine as Maven; only the wiring differs.

- **Install** — add to `build.gradle`:
  ```groovy
  testImplementation 'io.cucumber:cucumber-java:7.18.1'
  testImplementation 'io.cucumber:cucumber-junit-platform-engine:7.18.1'
  testImplementation 'org.junit.platform:junit-platform-suite:1.10.2'
  ```
- **Runner config** — ensure the `test` task uses the JUnit Platform and sees the feature resources:
  ```groovy
  test {
    useJUnitPlatform()
    systemProperty 'cucumber.junit-platform.naming-strategy', 'long'
  }
  ```
  Keep `.feature` files under `src/test/resources/features/` (same suite class as Maven).
- **Step stub:** identical to Maven (`io.cucumber.java.PendingException`).
- **Run:** `./gradlew test`
- **CI note:** Gradle writes JUnit XML under `build/test-results/test/`.

---

## C# — Reqnroll

- **Framework:** [Reqnroll](https://reqnroll.net/) — the actively-maintained, MIT-licensed successor to SpecFlow. **Prefer Reqnroll over SpecFlow:** identical API, but SpecFlow requires a commercial license for teams larger than one, while Reqnroll is free.
- **Install:** `dotnet add package Reqnroll.xUnit` (or `Reqnroll.NUnit` / `Reqnroll.MsTest` to match the project's test runner).
- **Directory layout:**
  - `Features/` — `.feature` files (set as `AdditionalFiles` / Reqnroll items).
  - `StepDefinitions/` — `[Binding]` step classes.
- **Runner config** — `reqnroll.json` at the project root:
  ```json
  { "language": { "feature": "en" } }
  ```
- **Step stub (pending):** inject `ScenarioContext` via the constructor and call `StepIsPending()` on the instance (it is not a static method):
  ```csharp
  using Reqnroll;

  [Binding]
  public class Steps {
    private readonly ScenarioContext _scenarioContext;
    public Steps(ScenarioContext scenarioContext) => _scenarioContext = scenarioContext;

    [Given("a precondition")]
    public void GivenAPrecondition() => _scenarioContext.StepIsPending();
  }
  ```
- **Run:** `dotnet test`
- **CI note:** `dotnet test --logger "junit;LogFilePath=reports/reqnroll-junit.xml"` (via the JUnit test logger) produces JUnit XML for the pipeline.

---

## Go — Godog

- **Framework:** [Godog](https://github.com/cucumber/godog) — the official Cucumber implementation for Go.
- **Install:** `go get github.com/cucumber/godog/cmd/godog@latest` (the library is pulled in transitively; the CLI is optional).
- **Directory layout:**
  - `features/` — `.feature` files.
  - step definitions live in a `*_test.go` file beside the suite entry point.
- **Runner config** — a suite entry point in `*_test.go` so Godog runs inside `go test` (no separate binary):
  ```go
  func TestFeatures(t *testing.T) {
    suite := godog.TestSuite{
      ScenarioInitializer: InitializeScenario,
      Options: &godog.Options{Format: "junit", Paths: []string{"features"}, TestingT: t},
    }
    if suite.Run() != 0 { t.Fatal("non-zero status returned, failed to run feature tests") }
  }
  ```
- **Step stub (pending):**
  ```go
  func aPrecondition() error { return godog.ErrPending }

  func InitializeScenario(sc *godog.ScenarioContext) {
    sc.Step(`^a precondition$`, aPrecondition)
  }
  ```
- **Run:** `go test ./...` (the suite runs as an ordinary Go test).
- **CI note:** with the `TestingT` option set (above), scenario failures surface as normal `go test` results, so the existing pipeline already sees them. For a separate JUnit-XML artifact, point `Options.Output` at a file writer (e.g. `f, _ := os.Create("reports/godog-junit.xml"); opts.Output = f`) with `Format: "junit"`.
