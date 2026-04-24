# Spec: Multi-Language SAST Auto-Dispatch

**Target plugin:** `plugins/agentic-security-review`
**Target release:** 0.4.0
**Status:** Ready for /plan

## Intent Description

The agentic-security-review plugin currently dispatches SAST tools without awareness of the target language. Non-.NET targets (Java, Go, Python, JavaScript, TypeScript) receive only generic semgrep coverage, leaving language-specific vulnerability classes undetected and giving users no signal that coverage is thin.

This change extends Phase 1 (tool-first detection) with automatic language detection. A new detection step inspects the target tree — file extensions plus build manifests (`pom.xml`, `build.gradle`, `go.mod`, `requirements.txt`, `pyproject.toml`, `package.json`, `tsconfig.json`, `*.csproj`, `*.sln`) — and emits a `memory/languages-<slug>.json` manifest. Per-language scanner scripts read the manifest and no-op unless their language is present. Outputs normalize through the existing SARIF → unified-finding pipeline so Phase 2+ sees consistent data regardless of source language. All dispatch is automatic; no user prompt.

## User-Facing Behavior

```gherkin
Feature: Multi-language SAST auto-dispatch
  As a security reviewer invoking /security-assessment
  I want the pipeline to detect target languages and run language-specific scanners
  So that non-.NET codebases receive complete SAST coverage without manual configuration

  Background:
    Given the agentic-security-review plugin is installed
    And required SAST tools are available on PATH

  Scenario: Java-only repository is fully scanned
    Given a target directory containing .java files and a pom.xml
    When /security-assessment runs against the target
    Then memory/languages-<slug>.json lists "java" with fileCount > 0
    And memory/semgrep-java-<slug>.sarif exists with findings from p/java, p/findsecbugs-rules, p/owasp-top-ten
    And memory/pmd-<slug>.sarif exists using knowledge/pmd-security-filter.xml
    And trivy fs --scanners vuln runs against pom.xml and its SCA findings land in memory/findings-<slug>.jsonl
    And every entry in memory/findings-<slug>.jsonl conforms to security-primitives-contract v1.0.0

  Scenario: Monorepo with Java, Go, Python, and TypeScript
    Given a target directory with .java, .go, .py, and .ts files
    When /security-assessment runs against the target
    Then memory/languages-<slug>.json lists "java", "go", "python", "typescript"
    And scan-java.sh, scan-go.sh, scan-python.sh, scan-js-ts.sh all execute
    And their outputs merge into a single memory/findings-<slug>.jsonl
    And each finding carries a sourceLanguage tag matching its scanner

  Scenario: Repository with no supported languages
    Given a target directory containing only Markdown and YAML
    When /security-assessment runs against the target
    Then memory/languages-<slug>.json lists zero languages
    And no scan-<lang>.sh scripts execute
    And Phase 1 completes with exit code 0

  Scenario: Java sources present but no compiled artifacts
    Given a target directory with .java files but no target/*.jar or build/libs/*.jar
    When scan-java.sh runs
    Then SpotBugs + FindSecBugs are skipped
    And memory/meta-<slug>.json records phase1.java.spotbugs_skipped = "no compiled artifacts"
    And semgrep and PMD still run to completion

  Scenario: Required tool is missing
    Given a target with .java files
    And pmd is not on PATH
    When scan-java.sh runs
    Then semgrep still executes
    And memory/meta-<slug>.json records phase1.java.pmd_skipped = "binary not found"
    And the script exits 0

  Scenario: PMD noise filter is applied by default
    Given a target with 150 .java files
    When scan-java.sh runs PMD
    Then the ruleset used is knowledge/pmd-security-filter.xml
    And findings are limited to security-category + hand-picked errorprone rules
    And AvoidCatchingGenericException, GuardLogStatement, MissingOverride do NOT appear in the PMD SARIF

  Scenario: Build file present but no source files
    Given a target containing package.json but zero .js or .ts files
    When language detection runs
    Then "javascript" is recorded with fileCount = 0 and confidence = "low"
    And buildFiles lists "package.json"
    And scan-js-ts.sh runs anyway and produces an empty SARIF

  Scenario: Phase 1 sub-timings run in parallel
    Given a target with Java, Go, and Python sources
    When Phase 1 runs
    Then the pipeline timing log records sub-timings phase-1-java, phase-1-go, phase-1-python
    And their wall-clock windows overlap (sum of durations > max of durations)
```

## Architecture Specification

### Components

| Component | Type | Purpose |
|-----------|------|---------|
| `skills/security-assessment-pipeline/SKILL.md` | Modify | Add Phase 1.0 (language detection); declare parallel sub-timings |
| `scripts/detect-languages.sh` | New | Produces `memory/languages-<slug>.json` |
| `scripts/scan-java.sh` | New | Semgrep (Java packs) + PMD (filtered) + Trivy fs (if pom/gradle) + SpotBugs (if artifacts) |
| `scripts/scan-go.sh` | New | gosec + staticcheck + govulncheck |
| `scripts/scan-python.sh` | New | Semgrep (p/python) + bandit + pip-audit |
| `scripts/scan-js-ts.sh` | New | Semgrep (p/javascript, p/typescript) + npm audit + eslint-plugin-security |
| `knowledge/pmd-security-filter.xml` | New | PMD ruleset referencing only security-category + hand-picked errorprone rules (remote refs, no rule bodies) |
| `CHANGELOG.md` | Modify | 0.4.0 entry |
| `CLAUDE.md` | Modify | Language-detection contract + "how to add a language" procedure |
| `commands/security-assessment.md` | Modify | Note auto-detection and per-language dispatch |

### Interfaces

**Language manifest — `memory/languages-<slug>.json`:**
```json
{
  "slug": "processing-atmserver",
  "targetPath": "targets/spshared/processing-atmserver",
  "detectedAt": "2026-04-23T15:00:00Z",
  "languages": [
    {
      "id": "java",
      "fileCount": 152,
      "buildFiles": ["pom.xml"],
      "confidence": "high"
    }
  ]
}
```

Supported language IDs (v1): `java`, `go`, `python`, `javascript`, `typescript`, `csharp`.
Confidence rule: `high` if both source files and build files present; `medium` if source files only; `low` if build files only.

**Scanner script contract:**
- Inputs: `--slug <slug>`, `--target <path>`, `--manifest memory/languages-<slug>.json`
- Reads the manifest; no-ops (exit 0) if its language is absent
- Writes SARIF to `memory/<tool>-<lang>-<slug>.sarif` (e.g. `memory/semgrep-java-processing-atmserver.sarif`, `memory/pmd-processing-atmserver.sarif`)
- Writes skips and warnings to `memory/meta-<slug>.json` under `phase1.<lang>.<tool>_skipped = "<reason>"`
- Exits 0 on no-op, on missing-tool skip, and on clean success; non-zero only on tool crash

**Finding envelope:** `security-primitives-contract v1.0.0`. Every SARIF output from every scanner is normalized through the existing `static-analysis-integration` normalizer. The normalizer must recognize the new filename pattern `<tool>-<lang>-<slug>.sarif`. Each normalized finding carries a `sourceLanguage` field set from the SARIF filename's `<lang>` segment.

**Pipeline dispatch:**
- Phase 1.0 (sequential): `detect-languages.sh` writes manifest
- Phase 1 (parallel, bash background jobs + `wait`): all applicable `scan-<lang>.sh` run concurrently
- Phase 1.5 (sequential): normalizer ingests SARIF files → appends to `memory/findings-<slug>.jsonl`
- Phase 1 timing log records each `phase-1-<lang>` sub-timing with start, end, and duration

### Style conventions

All new scripts mirror the header, `set -euo pipefail` usage, logging prefix, and argument-parsing pattern of the existing `scripts/check-severity-consistency.sh` and `scripts/verify-report.sh`.

### Dependencies

- No bundled rule packs. `pmd-security-filter.xml` references remote PMD categories by name only; no rule bodies.
- Runtime fetch from semgrep/PMD registries on first run (warms local tool caches).
- No paid/cloud tools (SonarQube Server, Checkmarx, Snyk cloud — excluded).
- No build orchestration. SpotBugs runs only against pre-existing `target/*.jar` or `build/libs/*.jar`.

### Non-goals

- `harness/redteam/*` is untouched.
- No changes to existing .NET scanner logic (assumed already emitting to the contract).
- No opt-in flag for full PMD ruleset — the security filter is the only supported ruleset.
- No Rust, Ruby, or PHP support in this release.
- No Java source compilation to enable SpotBugs.

## Acceptance Criteria

| # | Criterion | Pass condition |
|---|-----------|---------------|
| 1 | Detection manifest present | `memory/languages-<slug>.json` exists after Phase 1.0 and validates against the schema in Architecture Spec |
| 2 | Java scanner pack runs end-to-end | Running `/security-assessment targets/spshared/processing-atmserver` produces `memory/semgrep-java-processing-atmserver.sarif` containing rule hits from p/java, p/findsecbugs-rules, and p/owasp-top-ten |
| 3 | PMD noise is filtered | On a ≥150-file Java target, the PMD SARIF contains zero findings from rule IDs `AvoidCatchingGenericException`, `GuardLogStatement`, `MissingOverride` |
| 4 | Multi-language merge | On a Java+Go+Python target, `memory/findings-<slug>.jsonl` contains entries tagged `sourceLanguage: "java"`, `"go"`, and `"python"` — all in the same file |
| 5 | Envelope conformance | Every line in `memory/findings-<slug>.jsonl` validates against `security-primitives-contract v1.0.0` |
| 6 | Graceful tool-missing | With `pmd` uninstalled, `scan-java.sh` exits 0 and records `phase1.java.pmd_skipped = "binary not found"` in `memory/meta-<slug>.json` |
| 7 | No-op on unsupported targets | Running against a docs-only repo produces a manifest with empty `languages` array; no `scan-<lang>.sh` processes launched; pipeline exits 0 |
| 8 | Parallel dispatch observable | Pipeline timing output contains `phase-1-java`, `phase-1-go`, `phase-1-python`, `phase-1-js-ts` sub-timings; their wall-clock windows overlap for any multi-language target |
| 9 | Non-goal honored | `git diff` shows zero changes under `harness/redteam/`; no rule-pack bodies bundled; only `pmd-security-filter.xml` added to `knowledge/` |
| 10 | Documentation current | `CHANGELOG.md` has 0.4.0 entry; `CLAUDE.md` documents the language-detection contract and the procedure for adding a new language; `commands/security-assessment.md` notes auto-detection and dispatch |

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret "detect languages and dispatch per-language SAST with normalized envelopes" the same way
- [x] Every behavior has a corresponding BDD scenario — java-only, monorepo, no-supported-lang, spotbugs-skip, tool-missing, pmd-noise, low-confidence, parallel-timing all covered
- [x] Architecture constrains without over-engineering — specifies contracts, filenames, dispatch mechanism; reuses existing normalizer; no speculative abstractions
- [x] Terminology consistent across artifacts — `slug`, `manifest`, `envelope`, `sourceLanguage`, `security-primitives-contract v1.0.0` used uniformly
- [x] No contradictions — bundled PMD filter XML references remote categories only, consistent with the "no bundled rule packs" non-goal

**Verdict: PASS**

## Handoff Notes

This spec targets a **sibling plugin** (`plugins/agentic-security-review`), not the current working repo. The `/specs` skill's auto-trigger of `/plan` is intentionally suppressed — `/plan` should be invoked from within a session scoped to the target plugin, using this file as input.

To kick off implementation:
```
cd plugins/agentic-security-review
# start a fresh session, then:
/plan @docs/specs/multi-language-sast.md
```
