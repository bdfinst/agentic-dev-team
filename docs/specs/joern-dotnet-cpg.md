# Spec: Joern CPG build for .NET repos

Source prompt: [`.prompts/security-review-joern-dotnet-cpg.md`](../../.prompts/security-review-joern-dotnet-cpg.md)
Target plugin: `plugins/agentic-security-review/`

## Intent Description

The `agentic-security-review` plugin promises a hybrid false-positive-reduction pathway: joern-driven call-graph reachability when available, LLM fallback when not. In practice, every .NET scan silently degrades to LLM fallback because (a) the install scripts do not provision joern's C# frontend and (b) the runtime wrapper invokes `joern-parse` without `--language csharp`, so joern's autodetect misfires on .NET solutions. .NET is the dominant target ecosystem for this plugin in enterprise use, so the "hybrid when available" half of the value proposition never fires for the most common case.

This change closes both gaps in one PR: install-time provisioning of joern + C# frontend (or a clear operator warning when unavailable), and runtime language detection in the reachability wrapper so `--language csharp` is passed for .NET repos. The LLM-fallback path is preserved as the safety net; this work only makes the tool-first path actually fire for C#.

## User-Facing Behavior

```gherkin
Feature: Joern CPG reachability for .NET repositories

  Scenario: Security assessment against a .NET repo uses joern CPG reachability
    Given joern and its C# frontend are installed on the scan host
    And a target .NET repository containing .csproj and .cs files
    When I run /security-assessment against the target
    Then the disposition register entries carry reachability_tool: joern-cpg
    And no entry carries reachability_tool: llm-fallback due to missing CPG
    And exec-report-generator Section 6 does not list "joern CPG not built" for the .NET target

  Scenario: Security assessment against a non-.NET repo still uses the correct language
    Given joern is installed with the relevant frontend for the target language
    And a target repository whose primary language is Node/Python/Java/Go
    When I run /security-assessment against the target
    Then the disposition register entries carry reachability_tool: joern-cpg
    And the CPG cache file is named "<sha>.<language>.cpg"

  Scenario: joern is not installed on the scan host
    Given joern is not present on PATH
    When reachability.sh runs against any target
    Then reachability.sh exits 1
    And the fp-reduction agent proceeds with LLM fallback
    And the disposition register entries carry reachability_tool: llm-fallback

  Scenario: joern CPG build fails on a malformed .NET target
    Given joern and its C# frontend are installed
    And a target .NET repository that joern cannot parse (e.g., unsupported TFM)
    When reachability.sh runs against the target
    Then reachability.sh exits 2
    And the caller logs a structured reason
    And the caller does not crash

  Scenario: Operator runs install.sh without joern present
    Given joern is not installed on the host
    When the operator runs install.sh or install-macos.sh
    Then the install script prints a clear actionable warning naming "LLM-fallback mode"
    And the install script links to joern's install docs
    And the install script exits successfully (does not block plugin install)

  Scenario: Install-time verification of the C# frontend
    Given install.sh has installed joern and the C# frontend
    When the install script runs the verification step against the fixture .cs file
    Then joern-parse produces a non-empty CPG against knowledge/fixtures/joern-dotnet/
    And the install script reports success
    And failure of this verification fails the install script with a clear message

  Scenario: End-to-end fixture verifies joern ran (not LLM-generated narrative)
    Given a 20-line .cs fixture with a known source-to-sink SQLi chain
    When /security-assessment runs against the fixture directory with joern installed
    Then the SQLi finding's reachability_trace references specific CPG node IDs
    And the reachability_trace is not an LLM-generated narrative

  Scenario: Cache key includes language tag to avoid collisions
    Given two targets at the same commit SHA but different primary languages
    When reachability.sh runs for each
    Then the cache files are named "<sha>.csharp.cpg" and "<sha>.javascript.cpg" respectively
    And neither overwrites the other
```

## Architecture Specification

**Components modified**

- `plugins/agentic-security-review/install.sh` — add joern + C# frontend provisioning (or clear operator warning) and a post-install verification step against a fixture.
- `plugins/agentic-security-review/install-macos.sh` — same provisioning + verification, macOS-adapted.
- `plugins/agentic-security-review/skills/false-positive-reduction/tools/reachability.sh` — add language detection and pass `--language <lang>` to `joern-parse`.
- `plugins/agentic-security-review/knowledge/fixtures/joern-dotnet/` — new fixture `.cs` file with a deterministic source→sink chain.

**Components not modified**

- `skills/false-positive-reduction/SKILL.md` — promise is already correct; only the implementation underneath is off.
- `agents/fp-reduction` agent — already consumes CPG JSON correctly; the gap is upstream.
- `exec-report-generator` — consumer of the disposition register; benefits automatically when entries switch from `llm-fallback` to `joern-cpg`.

**Key interfaces**

- `reachability.sh` exit-code contract is load-bearing and must be preserved:
  - `0` = CPG built successfully
  - `1` = joern absent
  - `2` = CPG build failed
- Cache file naming changes from `<sha>.cpg` to `<sha>.<language>.cpg` — downstream consumers read via the wrapper, not direct filesystem access, so the rename is internal.

**Language detection rules** (first match wins)

| Signal files | `--language` value |
| --- | --- |
| `*.cs`, `*.csproj`, `*.sln` | `csharp` |
| `*.ts`, `*.tsx`, `*.js`, `package.json` | `javascript` |
| `*.py`, `pyproject.toml`, `requirements.txt` | `python` |
| `*.java`, `pom.xml`, `build.gradle` | `javasrc` |
| `*.go`, `go.mod` | `gosrc` |
| none of the above | (omit flag; joern autodetect) |

**Constraints**

- No new joern binary shipped with the plugin — Scala+JVM toolchain is too heavy for the install path. Detect-and-report is the chosen pattern.
- LLM-fallback path must remain functional and must not be removed.
- Existing cache-by-commit-SHA semantics at the top of `reachability.sh` are preserved; only the `joern-parse` invocation changes.
- The C# frontend is delivered separately from core joern (Scala module or `joern-cli-extras` / `dotnetastgen`). The install script must install whichever is current on the joern release tested; document the minimum version.

## Acceptance Criteria

- [ ] `tools/reachability.sh` classifies a target containing `.csproj`/`.sln`/`.cs` as `csharp` and invokes `joern-parse --language csharp`.
- [ ] `tools/reachability.sh` preserves the exit-code contract: 0 = built, 1 = joern absent, 2 = build failed.
- [ ] `tools/reachability.sh` writes cache files as `<sha>.<language>.cpg`.
- [ ] `install.sh` and `install-macos.sh` either install joern + C# frontend or emit a clearly-worded actionable warning naming "LLM-fallback mode" and linking to joern's install docs.
- [ ] The install scripts run a verification step that executes `joern-parse --language csharp` against `knowledge/fixtures/joern-dotnet/*.cs` and fails the install on non-zero CPG output.
- [ ] `knowledge/fixtures/joern-dotnet/` contains at least one `.cs` file with a deterministic source→sink chain (HTTP input → string-concat → SQL command).
- [ ] Running `/security-assessment` against `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/ivr` produces a disposition register whose entries carry `reachability_tool: joern-cpg`, not `llm-fallback`.
- [ ] `exec-report-generator` Section 6 "Coverage-gap callouts" no longer lists "joern CPG not built" for .NET targets.
- [ ] Regression: running against a non-.NET target (Node or Python repo) still selects the right language and still produces `reachability_tool: joern-cpg`.
- [ ] Fallback still works: running against a .NET repo with malformed solution exits 2 from `reachability.sh` and the caller logs a structured reason without crashing.
- [ ] Minimum joern version tested is documented in the install script header.
- [ ] CI passes.
- [ ] Post-merge smoke test against `/Users/finsterb/_git-aci/ng-security-scan/targets/spnextgen/login-service` confirms `reachability_tool: joern-cpg` in the disposition register.

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way
- [x] Every behavior in the intent has at least one corresponding BDD scenario
- [x] Architecture specification constrains implementation to what the intent requires, without over-engineering
- [x] Same concepts named consistently across all four artifacts (`reachability_tool`, `joern-cpg`, `llm-fallback`, exit codes 0/1/2)
- [x] No artifact contradicts another

**Scope note**: this spec bundles two logical slices (install-time provisioning + runtime language detection). They are bundled deliberately — the acceptance test (a .NET `/security-assessment` run producing `reachability_tool: joern-cpg`) fails unless both land together. Splitting would produce a half-shipped feature that still reports LLM-fallback. Bundle is correct.

**Verdict: PASS** — spec is ready for planning.
