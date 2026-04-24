# Plan: Multi-Language SAST Auto-Dispatch

**Created**: 2026-04-23
**Revised**: 2026-04-23 (post plan-review v1)
**Branch**: main
**Status**: draft (v2 — revised after plan review)
**Spec**: `docs/specs/multi-language-sast.md`

## Goal

Extend the agentic-security-assessment Phase 1 tool-first pipeline so it auto-detects target languages (Java, Go, Python, JavaScript, TypeScript, C#) and dispatches per-language SAST scanners in parallel. Outputs normalize through the existing SARIF → unified-finding pipeline, so Phase 2+ sees a consistent, single `findings-<slug>.jsonl` regardless of the target's language mix. Closes the silent Java coverage gap that motivated this work (`targets/spshared/processing-atmserver`).

## Acceptance Criteria

- [ ] `memory/languages-<slug>.json` exists after Phase 1.0 and conforms to the schema in the spec
- [ ] Running `/security-assessment targets/spshared/processing-atmserver` produces `memory/semgrep-java-processing-atmserver.sarif` whose SARIF `runs[].tool.driver.rules` references rules from p/java, p/findsecbugs-rules, and p/owasp-top-ten (invocation evidence, not finding counts)
- [ ] PMD SARIF on a ≥150-file Java target contains zero findings from `AvoidCatchingGenericException`, `GuardLogStatement`, `MissingOverride`
- [ ] `knowledge/pmd-security-filter.xml` contains zero `<rule>` element bodies — only `<rule ref="..."/>` remote references (lint: `grep -c '<rule [^r]' knowledge/pmd-security-filter.xml` must equal `0`)
- [ ] On a Java+Go+Python target, one `memory/findings-<slug>.jsonl` contains entries tagged `sourceLanguage` for each language
- [ ] Every line in `memory/findings-<slug>.jsonl` validates against `security-primitives-contract v1.0.0`
- [ ] With `pmd` uninstalled, `scan-java.sh` exits 0, writes `phase1.java.pmd_skipped = "binary not found"` to `memory/meta-<slug>.json`, **and emits a `stderr` line matching `[scan-java] WARN: pmd not on PATH`**
- [ ] When any single scanner's underlying tool crashes (non-zero exit), that scanner records the error to its meta fragment with exit code and continues peer scanners to completion; Phase 1 exits 0
- [ ] Malformed `memory/languages-<slug>.json` causes scanner scripts to exit non-zero with a parse error to stderr; no SARIF is written
- [ ] Docs-only target produces an empty languages list and launches zero scanner processes
- [ ] A C#-only target produces a manifest with `languages: [{id: "csharp", ...}]` and triggers no new `scan-<lang>.sh` dispatch (existing .NET scanner flow is unaffected)
- [ ] Phase 1 emits stdout progress: `[phase-1] detected <langs>; dispatching <N> scanners` at start, one `[phase-1-<lang>] done in <ms>ms (<tools-ran> ran, <tools-skipped> skipped)` per completion
- [ ] Pipeline timing log records `phase-1-java|go|python|js-ts` sub-timings with `max(end) - min(start) < sum(durationMs)` as the overlap proof (deterministic via test-only `PHASE1_FAKE_SLEEP_MS`)
- [ ] `harness/redteam/*` untouched
- [ ] CHANGELOG 0.4.0 entry + CLAUDE.md language-detection contract + `commands/security-assessment.md` auto-detection section + `README.md` accuracy review all complete

## User-Facing Behavior

```gherkin
Feature: Multi-language SAST auto-dispatch
  As a security reviewer invoking /security-assessment
  I want the pipeline to detect target languages and run language-specific scanners
  So that non-.NET codebases receive complete SAST coverage without manual configuration

  Background:
    Given the agentic-security-assessment plugin is installed
    And required SAST tools are available on PATH

  Scenario: Java-only repository is fully scanned
    Given a target directory containing .java files and a pom.xml
    When /security-assessment runs against the target
    Then memory/languages-<slug>.json lists "java" with fileCount > 0
    And memory/semgrep-java-<slug>.sarif exists whose tool.driver.rules references rules from p/java, p/findsecbugs-rules, and p/owasp-top-ten
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

  Scenario: C#-only target dispatches no new scanner
    Given a target directory with *.cs files and a *.csproj
    When /security-assessment runs against the target
    Then memory/languages-<slug>.json lists "csharp" with confidence "high"
    And scan-java.sh, scan-go.sh, scan-python.sh, scan-js-ts.sh are NOT invoked
    And the existing .NET scanner flow is unaffected

  Scenario: Java sources present but no compiled artifacts
    Given a target directory with .java files but no target/*.jar or build/libs/*.jar
    When scan-java.sh runs
    Then SpotBugs + FindSecBugs are skipped
    And memory/meta-<slug>.json records phase1.java.spotbugs_skipped = "no compiled artifacts"
    And semgrep and PMD still run to completion

  Scenario: Required tool is missing — user sees it on stderr
    Given a target with .java files
    And pmd is not on PATH
    When scan-java.sh runs
    Then semgrep still executes
    And memory/meta-<slug>.json records phase1.java.pmd_skipped = "binary not found"
    And stderr contains a line matching "[scan-java] WARN: pmd not on PATH"
    And the script exits 0

  Scenario: Scanner tool crashes — peer scanners continue
    Given a target with .java, .go, and .py files
    And the fake semgrep binary is configured to exit with code 2 when run for Java
    When Phase 1 dispatches all three scanners in parallel
    Then memory/meta-<slug>-java.json records phase1.java.semgrep_error = "exit 2"
    And scan-go.sh and scan-python.sh complete normally with SARIF outputs
    And run-phase1.sh exits 0
    And the post-wait merge step produces complete memory/meta-<slug>.json and memory/timings-<slug>.jsonl

  Scenario: Malformed language manifest
    Given memory/languages-<slug>.json is malformed JSON
    When scan-java.sh runs
    Then stderr contains a parse-error message naming the manifest path
    And the script exits with a non-zero code
    And no memory/semgrep-java-<slug>.sarif is written

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
    And scan-js-ts.sh runs anyway and produces a SARIF with a valid empty skeleton (runs[0].results = [])

  Scenario: User sees progress during parallel Phase 1
    Given a target with Java, Go, and Python sources
    When Phase 1 runs
    Then stdout contains a line matching "[phase-1] detected java, go, python; dispatching 3 scanners"
    And stdout contains one "[phase-1-<lang>] done in <n>ms" line per scanner completion
    And the pipeline timing log records sub-timings phase-1-java, phase-1-go, phase-1-python
    And max(end) - min(start) < sum(durationMs) across the three sub-timings
```

## Steps

### Step 1: Pre-requisite — locate the SARIF normalizer

**Complexity**: trivial (investigation; no production code change)
**RED**: N/A — spike.
**GREEN**: Grep the plugin + sibling `agentic-dev-team` plugin for the existing SARIF → unified-finding normalizer. Document findings in `docs/specs/normalizer-inventory.md`: absolute path, extension point, language/tool inference table, owner plugin. If the normalizer lives in the sibling plugin, document whether this plan may modify it or must wrap/extend it from this side (decision logged; re-ask user if ambiguous).
**REFACTOR**: None.
**Files**: `docs/specs/normalizer-inventory.md`
**Commit**: `docs: locate and document SARIF normalizer extension points`
**Gate**: If the normalizer does not exist, stop and escalate — that is a separate vertical slice that must precede this plan.

### Step 2: Introduce bats test harness + fixture library + fake-tool helpers

**Complexity**: standard
**RED**: Add `tests/run.sh` that invokes `bats tests/*.bats` and a placeholder `tests/smoke.bats` asserting `1 -eq 1`. Fails until bats is discoverable and fixtures are present.
**GREEN**: Add `tests/helpers/fake_tools.bash` (creates a `PATH`-shadowed temp dir where fake `semgrep`, `pmd`, `trivy`, `gosec`, `staticcheck`, `govulncheck`, `bandit`, `pip-audit`, `npm`, `eslint` binaries write their argv to a sentinel file, sleep `${PHASE1_FAKE_SLEEP_MS:-0}` ms, and exit with code `${PHASE1_FAKE_EXIT:-0}`). Add fixtures under `tests/fixtures/`: `java-only/`, `java-with-artifacts/`, `java-without-artifacts/`, `go-only/`, `python-only/`, `js-only/`, `ts-only/`, `csharp-only/`, `pkg-json-only/`, `docs-only/`, `monorepo/`. Smoke test passes.
**REFACTOR**: None.
**Files**: `tests/run.sh`, `tests/smoke.bats`, `tests/helpers/fake_tools.bash`, `tests/fixtures/**`, `tests/README.md` (bats install instructions)
**Commit**: `test: scaffold bats harness, fixtures, and fake-tool helpers`

### Step 3: Language detection script

**Complexity**: standard
**RED**: `tests/detect-languages.bats` cases: `java-only`, `docs-only`, `monorepo`, `pkg-json-only`, `csharp-only`, malformed-target. Assert `memory/languages-<slug>.json` matches schema `{slug, targetPath, detectedAt, languages: [{id, fileCount, buildFiles, confidence}]}`. Confidence rules: high = source + build, medium = source only, low = build only. `docs-only` yields `languages: []`.
**GREEN**: `scripts/detect-languages.sh` — thin bash wrapper that invokes an embedded **Python heredoc** for tree-walk + JSON assembly (matches the style of `scripts/verify-report.sh` and `scripts/check-severity-consistency.sh`). Header, `set -euo pipefail`, log prefix, arg parser mirror existing scripts.
**REFACTOR**: None.
**Files**: `scripts/detect-languages.sh`, `tests/detect-languages.bats`
**Commit**: `feat(scanners): add language detection manifest via Python-heredoc tree walk`

### Step 4: Scanner script contract — no-op on absent language, malformed-manifest handling, scanner-common.sh

**Complexity**: standard
**RED**: `tests/scanner-contract.bats` covers (a) manifest with `languages: []` → each `scan-<lang>.sh` exits 0, writes no SARIF, appends nothing to meta; (b) manifest missing → exit non-zero with stderr parse error; (c) manifest present but this scanner's language absent → exit 0, no outputs. Four scanners tested uniformly.
**GREEN**: Create `scripts/lib/scanner-common.sh` with shared helpers: `parse_args`, `load_manifest` (Python heredoc for robust JSON parsing), `language_present`, `record_skip lang tool reason`, `record_error lang tool exit_code`, `warn_stderr msg`, `start_timing tool`, `end_timing tool`. Create four scanner script stubs that source it. Each writes to **per-scanner fragment files**: `memory/fragments/meta-<slug>-<lang>.json` and `memory/fragments/timings-<slug>-<lang>.jsonl` — avoids concurrent-write races when dispatched in parallel (fragments merged in Step 12).
**REFACTOR**: None.
**Files**: `scripts/scan-java.sh`, `scripts/scan-go.sh`, `scripts/scan-python.sh`, `scripts/scan-js-ts.sh`, `scripts/lib/scanner-common.sh`, `scripts/lib/SCANNER-CONTRACT.md`, `tests/scanner-contract.bats`
**Commit**: `feat(scanners): scanner script contract with per-scanner fragment files`

### Step 5: Java — semgrep leg

**Complexity**: standard
**RED**: `tests/scan-java.bats` asserts that given a Java manifest, `scan-java.sh` calls `semgrep --config=p/java --config=p/findsecbugs-rules --config=p/owasp-top-ten --sarif --output memory/semgrep-java-<slug>.sarif <target>`. Verify via `fake_tools.bash` argv capture. Include a tool-crash case: when `PHASE1_FAKE_EXIT=2` is set for semgrep, `scan-java.sh` records `phase1.java.semgrep_error = "exit 2"` to its meta fragment and exits 0 (continues to PMD leg in later steps).
**GREEN**: Wire semgrep invocation. If semgrep binary absent, emit stderr WARN and record `phase1.java.semgrep_skipped = "binary not found"`; exit 0.
**REFACTOR**: None.
**Files**: `scripts/scan-java.sh`, `scripts/lib/scanner-common.sh`, `tests/scan-java.bats`
**Commit**: `feat(scan-java): dispatch semgrep with Java rule packs; handle crash + missing`

### Step 6: Java — PMD with security filter

**Complexity**: standard
**RED**: `tests/scan-java.bats` asserts (a) PMD invoked with `-R knowledge/pmd-security-filter.xml -f sarif -d <target> -r memory/pmd-<slug>.sarif`; (b) golden PMD SARIF fixture produces zero hits for `AvoidCatchingGenericException`, `GuardLogStatement`, `MissingOverride`; (c) lint: `grep -c '<rule [^r]' knowledge/pmd-security-filter.xml` equals `0`.
**GREEN**: Create `knowledge/pmd-security-filter.xml` referencing only `category/java/security.xml` + hand-picked errorprone rules (`AvoidUsingHardCodedIP`, `EmptyCatchBlock`, `HardCodedCryptoKey`, `InsecureCryptoIv`). No rule bodies — only `<rule ref="..."/>` entries. Wire PMD call in `scan-java.sh` with missing-tool stderr WARN + meta skip.
**REFACTOR**: None.
**Files**: `scripts/scan-java.sh`, `knowledge/pmd-security-filter.xml`, `tests/scan-java.bats`, `tests/fixtures/pmd-noise/`
**Commit**: `feat(scan-java): add PMD security-filter ruleset with remote-refs only`

### Step 7: Java — Trivy fs SCA on build manifest

**Complexity**: standard
**RED**: `tests/scan-java.bats` asserts that when `pom.xml` or `build.gradle` is in the manifest's `buildFiles`, `trivy fs --scanners vuln --format sarif --output memory/trivy-java-<slug>.sarif <build-file>` runs. When absent, trivy is not invoked. Tool-missing: stderr WARN + skip meta; exit 0.
**GREEN**: Conditional trivy call.
**REFACTOR**: None.
**Files**: `scripts/scan-java.sh`, `tests/scan-java.bats`
**Commit**: `feat(scan-java): add trivy SCA on pom/gradle`

### Step 8: Java — SpotBugs/FindSecBugs conditional on compiled artifacts

**Complexity**: standard
**RED**: `tests/scan-java.bats` case `java-without-artifacts` asserts SpotBugs NOT invoked and `meta-<slug>-java.json` contains `phase1.java.spotbugs_skipped = "no compiled artifacts"`. Case `java-with-artifacts` (fixture has `target/app.jar`) asserts SpotBugs IS invoked with FindSecBugs plugin flag and writes `memory/spotbugs-<slug>.sarif`.
**GREEN**: Artifact detection in `scan-java.sh`: `find <target> -type f \( -path '*/target/*.jar' -o -path '*/build/libs/*.jar' \) | head -1`. Invoke SpotBugs only when present; no build orchestration.
**REFACTOR**: None. Size check: if `scan-java.sh` exceeds 150 lines after this step, note as candidate for sub-script decomposition in a future refactor (deferred per plan review v1 decision); do not split now.
**Files**: `scripts/scan-java.sh`, `tests/scan-java.bats`, `tests/fixtures/java-with-artifacts/`
**Commit**: `feat(scan-java): conditional SpotBugs+FindSecBugs on pre-built artifacts`

### Step 9: Go scanner pack

**Complexity**: standard
**RED**: `tests/scan-go.bats` asserts gosec, staticcheck, govulncheck each invoked with the target, each writing SARIF to `memory/gosec-<slug>.sarif` / `memory/staticcheck-<slug>.sarif` / `memory/govulncheck-<slug>.sarif`. Tool-missing → stderr WARN + meta skip. Tool crash → meta error + peers continue. No-op when `go` absent from manifest.
**GREEN**: Flesh out `scan-go.sh` per contract.
**REFACTOR**: None.
**Files**: `scripts/scan-go.sh`, `tests/scan-go.bats`, `tests/fixtures/go-only/`
**Commit**: `feat(scan-go): dispatch gosec, staticcheck, govulncheck`

### Step 10: Python scanner pack

**Complexity**: standard
**RED**: `tests/scan-python.bats` asserts semgrep (p/python), bandit, and pip-audit all run with SARIF outputs under `memory/`. Standard no-op / missing / crash contract.
**GREEN**: Flesh out `scan-python.sh`.
**REFACTOR**: None.
**Files**: `scripts/scan-python.sh`, `tests/scan-python.bats`, `tests/fixtures/python-only/`
**Commit**: `feat(scan-python): dispatch semgrep, bandit, pip-audit`

### Step 11: JS/TS scanner pack

**Complexity**: standard
**RED**: `tests/scan-js-ts.bats` asserts semgrep (p/javascript, p/typescript), npm audit, and eslint with `eslint-plugin-security` all run. Build-file-only case produces a valid empty SARIF skeleton (`runs[0].results = []`). Standard no-op / missing / crash contract.
**GREEN**: Flesh out `scan-js-ts.sh`. Detect `package.json` to gate npm audit; detect `.ts/.tsx` to include TS pack.
**REFACTOR**: None.
**Files**: `scripts/scan-js-ts.sh`, `tests/scan-js-ts.bats`, `tests/fixtures/js-only/`, `tests/fixtures/ts-only/`, `tests/fixtures/pkg-json-only/`
**Commit**: `feat(scan-js-ts): dispatch semgrep, npm audit, eslint-plugin-security`

### Step 12: Parallel dispatch orchestrator, fragment merge, sub-timings

**Complexity**: complex
**RED**: `tests/phase1-dispatch.bats` on a java+go+python fixture with `PHASE1_FAKE_SLEEP_MS=200` asserts: (a) all three scanner scripts run; (b) stdout contains `[phase-1] detected java, go, python; dispatching 3 scanners` and three `[phase-1-<lang>] done in <ms>ms` lines; (c) after wait + merge, `memory/timings-<slug>.jsonl` contains `phase-1-java`, `phase-1-go`, `phase-1-python` entries with `start`, `end`, `durationMs`; (d) `max(end) - min(start) < sum(durationMs)` (deterministic overlap proof); (e) `memory/meta-<slug>.json` is a clean merged structure (no fragment files left behind); (f) one scanner crash (`PHASE1_FAKE_EXIT=2` on one scanner) does not abort peers and the crash is recorded in merged meta.
**GREEN**: Add `scripts/run-phase1.sh`. Reads manifest, launches each applicable `scan-<lang>.sh` as a background job, uses `wait` with per-PID status capture. After all `wait` calls complete, sequentially merges `memory/fragments/meta-<slug>-*.json` → `memory/meta-<slug>.json` and `memory/fragments/timings-<slug>-*.jsonl` → `memory/timings-<slug>.jsonl` (Python heredoc does the merge for robustness). Emits `[phase-1] detected ...; dispatching N scanners` on stdout at dispatch; per-scanner completion lines as each `wait` resolves. Registers a trap that cleans up orphaned children on SIGINT. Extracts PID/timing management into `scripts/lib/parallel.sh`.
**REFACTOR**: None.
**Files**: `scripts/run-phase1.sh`, `scripts/lib/parallel.sh`, `tests/phase1-dispatch.bats`, `tests/fixtures/monorepo/`
**Commit**: `feat(pipeline): parallel phase-1 dispatch with fragment merge and sub-timings`

### Step 13: Normalizer extension — filename patterns + sourceLanguage tag

**Complexity**: complex
**RED**: `tests/normalizer.bats` feeds fixture SARIF files named `semgrep-java-<slug>.sarif`, `pmd-<slug>.sarif`, `trivy-java-<slug>.sarif`, `spotbugs-<slug>.sarif`, `gosec-<slug>.sarif`, `staticcheck-<slug>.sarif`, `govulncheck-<slug>.sarif`, `semgrep-python-<slug>.sarif`, `bandit-<slug>.sarif`, `pip-audit-<slug>.sarif`, `semgrep-javascript-<slug>.sarif`, `semgrep-typescript-<slug>.sarif`, `eslint-<slug>.sarif`, `npm-audit-<slug>.sarif` through the normalizer. Assert every emitted record in `memory/findings-<slug>.jsonl` conforms to `security-primitives-contract v1.0.0` and carries the correct `sourceLanguage`. Includes a negative case: an unknown `foo-bar.sarif` is logged and skipped (not errored out).
**GREEN**: Update the normalizer identified in Step 1 to (a) recognize `<tool>-<lang>-<slug>.sarif` and `<tool>-<slug>.sarif` patterns, (b) stamp `sourceLanguage` using a mapping table (pmd → java, gosec/staticcheck/govulncheck → go, bandit/pip-audit → python, eslint/npm-audit → javascript-or-typescript by manifest confidence, etc.), (c) log-and-skip unknown filenames.
**REFACTOR**: Consolidate filename-parsing into one helper; extract the tool→language mapping into a data-only file for testability.
**Files**: normalizer path from Step 1, associated tests, tool-to-language mapping data file
**Commit**: `feat(normalizer): recognize per-language SARIF filenames and tag sourceLanguage`

### Step 14: Pipeline skill integration

**Complexity**: standard
**RED**: `tests/pipeline-integration.bats` runs Phase 1 end-to-end against `tests/fixtures/monorepo/` and asserts: manifest present, all applicable scanners' SARIFs present, single `findings-<slug>.jsonl` with all applicable `sourceLanguage` values, merged `meta-<slug>.json` populated, `timings-<slug>.jsonl` complete, stdout progress lines present.
**GREEN**: Edit `skills/security-assessment-pipeline/SKILL.md` — insert Phase 1.0 (`detect-languages.sh`) and Phase 1 (`run-phase1.sh`) in the skill graph. Update the phase-timing table with `phase-1-java`, `phase-1-go`, `phase-1-python`, `phase-1-js-ts` as sub-timings under Phase 1. Reference envelope contract by version.
**REFACTOR**: None.
**Files**: `skills/security-assessment-pipeline/SKILL.md`, `tests/pipeline-integration.bats`
**Commit**: `feat(pipeline): wire language detection + parallel dispatch into Phase 1`

### Step 15: End-to-end acceptance run on processing-atmserver

**Complexity**: standard
**RED**: `tests/e2e-processing-atmserver.bats` (opt-in via env `ADT_E2E=1`, documented in quality gate). Invokes `/security-assessment targets/spshared/processing-atmserver` through the public entry point. Asserts `memory/semgrep-java-processing-atmserver.sarif` exists and its `runs[].tool.driver` references rules from all three packs (invocation evidence). Asserts `findings-<slug>.jsonl` lines all conform to `security-primitives-contract v1.0.0`.
**GREEN**: No new code — this test either passes because prior steps are correct, or it reveals a gap to fix in the relevant earlier step.
**REFACTOR**: None.
**Files**: `tests/e2e-processing-atmserver.bats`
**Commit**: `test(e2e): acceptance run on processing-atmserver target`

### Step 16: Documentation — CHANGELOG, CLAUDE.md, command doc, README accuracy pass

**Complexity**: standard
**RED**: Doc-review checklist embedded in the commit body must be verifiable:
- CHANGELOG has 0.4.0 entry describing multi-language SAST dispatch and the envelope contract.
- CLAUDE.md has a new section "Language detection contract" (schema + confidence rules + fragment/merge model) and "Adding a new language" procedure (name the scanner file, map the tool→language entry, add a fixture, add a bats file).
- `commands/security-assessment.md` has a new "Auto-detection and dispatch" section that lists (a) what languages are auto-detected, (b) tools run per language, (c) where to look on skip (`stderr` + `meta-<slug>.json`), (d) how to add a language (pointer to CLAUDE.md), (e) an ASCII pipeline diagram: `detect-languages.sh → run-phase1.sh → [scan-java | scan-go | scan-python | scan-js-ts] → normalizer → findings-<slug>.jsonl`.
- **README.md accuracy review**: read the current README end-to-end; verify every claim still holds (feature list, supported languages, install commands, example output). Update: add multi-language dispatch to feature list; correct any drift between README and CLAUDE.md / commands/ / skills/; update any stale slash-command or script references.
**GREEN**: Edit the four docs files.
**REFACTOR**: None.
**Files**: `CHANGELOG.md`, `CLAUDE.md`, `commands/security-assessment.md`, `README.md`
**Commit**: `docs: 0.4.0 multi-language SAST dispatch + README accuracy pass`

## Complexity Classification

- **trivial**: Step 1 (spike, no code).
- **standard**: Steps 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16 — new scripts and tests within established patterns.
- **complex**: Steps 12 and 13 — parallel dispatch correctness (races, crash handling) and envelope-contract conformance across the full normalizer pipeline.

## Pre-PR Quality Gate

- [ ] `tests/run.sh` (all bats tests) pass
- [ ] `shellcheck scripts/*.sh scripts/lib/*.sh tests/**/*.sh` passes
- [ ] `grep -c '<rule [^r]' knowledge/pmd-security-filter.xml` equals `0` (no bundled rule bodies)
- [ ] Every line in `memory/findings-<slug>.jsonl` validates against `security-primitives-contract v1.0.0`
- [ ] `/code-review` passes (structure, security, complexity, naming, doc, concurrency-review required for Step 12)
- [ ] E2E acceptance run against `targets/spshared/processing-atmserver` passes with `ADT_E2E=1`
- [ ] Docs verified: CHANGELOG 0.4.0, CLAUDE.md contract, `commands/security-assessment.md` auto-detection section, `README.md` accuracy pass

## Risks & Open Questions

- **Normalizer location (addressed in Step 1).** Moved from Risks to a hard pre-requisite. Plan halts if Step 1 cannot locate the normalizer — that's a separate slice.
- **Tool version drift.** gosec, PMD, bandit rule IDs change between versions; golden-SARIF fixtures can go stale. Mitigation: add a `scripts/install-sast-tools.sh` with pinned versions as part of Step 2 (dev setup); assert on rule *categories* rather than exact IDs where possible.
- **Parallelism resource fan-out.** A huge monorepo fans out 10+ concurrent tool processes. Out of scope for 0.4.0 — note `ADT_PHASE1_MAX_PARALLEL` env var for 0.4.1.
- **PMD remote rule availability.** If PMD's remote rule schema changes or categories move, `pmd-security-filter.xml` breaks at runtime. Mitigation: pin PMD version in `install-sast-tools.sh`; document in CLAUDE.md.
- **Scope size — acknowledged override.** The Strategic plan reviewer flagged 15-step scope as a blocker and recommended splitting Java-only to 0.4.0, rest to 0.4.1. User direction is to ship all five languages as one change; accepted and logged. This concentrates release risk — mitigated by the scanner contract (Step 4) being proven on Java first (Steps 5–8) and only then extended uniformly to Go/Python/JS-TS (Steps 9–11).
- **fake-tool PATH-shadowing coverage.** Bats fixtures verify argv shape, not real-tool behavior. Mitigation: Step 15's E2E runs real tools against the motivating target.

## Plan Review Summary (v2 — post revision)

**Acceptance Test Critic:** approve. All four prior blockers (flaky timing, missing crash scenario, missing malformed-manifest scenario, missing C# handling) addressed with concrete test hooks and acceptance criteria, not just prose.
**Design & Architecture Critic:** approve. Fragment-files-then-merge eliminates the parallel write-contention race by design. Normalizer dependency promoted to a pre-requisite spike (Step 1) with an explicit escalation gate.
**UX Critic:** approve. Stdout progress lines + stderr WARN on missing tools are now acceptance criteria with dedicated Gherkin scenarios. Mental-model documentation (ASCII pipeline diagram) included in Step 16.
**Strategic Critic:** acknowledged and overridden per user direction to ship as one change. Release-risk concentration is mitigated by proving the scanner contract on Java first (Steps 5–8) before uniform extension to Go/Python/JS-TS (Steps 9–11).

### Non-blocking warnings to be aware of during implementation

- **Acceptance (minor):** Empty-SARIF skeleton scenario doesn't name which tool authors the skeleton when multiple fake tools run. Scanner-internal-tool vs scanner-process crash distinction is implicit — disambiguate in `scripts/lib/SCANNER-CONTRACT.md` (Step 4).
- **Design (minor):** `scanner-common.sh` now owns 7 responsibilities. If any helper signature churns during Steps 5–11, consider splitting reporting helpers (`record_skip`, `record_error`, `warn_stderr`, timing) into `scripts/lib/scanner-reporting.sh`.
- **Design (minor):** `scripts/lib/parallel.sh` is extracted in Step 12 with only one caller. Inlining in `run-phase1.sh` and extracting later when a second caller appears would match YAGNI.
- **UX (minor, 0.4.1 material):** Progress line could name skipped tools (e.g. `1 skipped: pmd`). No `--quiet` flag for stderr WARN floods on targets missing many optional tools.

None of these block `/build`. Surface them as refactor candidates during the TDD REFACTOR phase of the affected steps.
