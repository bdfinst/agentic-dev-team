# Spec: Semantic Duplication Scan

## Intent Description

This feature adds a `/semantic-scan` skill and command that detects business logic reimplemented multiple times across different architectural layers. Traditional linters and existing review agents catch syntactic similarity or single-instance layer violations — they cannot detect when the same domain calculation independently appears in multiple places with different variable names and structure.

The skill runs in two modes. On first run (**full scan**), it scans the codebase, annotates each non-trivial computation function with a structured semantic description, and writes a persistent `computation-register.json` to the project root. On subsequent runs (**incremental scan**), it uses `git diff` to identify only changed files, re-annotates those files, and updates the register.

A **trivial function** — one that performs no calculations and does not modify state — is excluded from the register regardless of language. Concretely: a function is trivial if it contains no arithmetic operators, no boolean logic, no branching constructs, no assignments to variables outside its own scope, and no calls to higher-order collection operations (map, filter, reduce).

Layer identification is inferred from each function's **coupling profile** (what it imports, what concerns it touches, what it depends on) rather than directory conventions. Annotation is language-agnostic.

After building or updating the register, the skill runs a clustering pass to find semantic duplicates across layers. For each cluster, it suggests the most likely canonical location but marks all canonical designations as requiring human confirmation — because the canonical may not yet exist.

Integration with `/code-review` is out of scope for this slice.

## User-Facing Behavior

```gherkin
Feature: Semantic Duplication Scan

  Background:
    Given a project with source files in any language

  Scenario: First-time full scan creates a computation register
    Given no computation-register.json exists in the project root
    When the developer runs /semantic-scan
    Then computation-register.json is created at the project root
    And it contains one entry per non-trivial computation identified
    And each entry contains: file path, function name, inferred layer, structured semantic description, prompt version, and HEAD commit hash
    And functions that perform no calculations and do not modify state are excluded
    And the developer sees progress output as each file is annotated: "Annotating [N/total] <filename>"

  Scenario: Annotation failure is reported, not silenced
    Given a full scan is running
    And annotation fails for one file due to a transient LLM error
    When the scan completes
    Then the register is written with all successfully annotated files
    And the register includes a scanErrors array identifying the failed file and error reason
    And the developer sees a warning: "Warning: 1 file could not be annotated. Re-run /semantic-scan to retry."
    And the scan exits with code 0

  Scenario: Incremental scan re-annotates only changed files
    Given computation-register.json exists with a lastScanCommit recorded
    And that commit exists in the full git history
    And 5 source files have been modified or added since that commit
    And 95 source files have not changed
    When the developer runs /semantic-scan
    Then only the 5 changed files are re-annotated
    And the 95 unchanged entries are preserved exactly
    And lastScanCommit is updated to HEAD

  Scenario: Incremental scan with no changed files updates only lastScanCommit
    Given computation-register.json exists with a lastScanCommit recorded
    And no source files have changed since that commit
    When the developer runs /semantic-scan
    Then no entries in the register are modified
    And lastScanCommit is updated to HEAD
    And the output reports "No changes since last scan — register up to date"

  Scenario: Deleted file is removed from the register
    Given computation-register.json exists with an entry for src/pricing/calculator.js
    And src/pricing/calculator.js has been deleted since lastScanCommit
    When the developer runs /semantic-scan
    Then the register entry for src/pricing/calculator.js is removed
    And lastScanCommit is updated to HEAD

  Scenario: --full flag forces full re-scan regardless of lastScanCommit
    Given computation-register.json exists with a valid lastScanCommit
    And no source files have changed since that commit
    When the developer runs /semantic-scan --full
    Then all files in scope are re-annotated
    And lastScanCommit is updated to HEAD

  Scenario: Shallow clone detected in incremental mode
    Given computation-register.json exists with a lastScanCommit recorded
    And the repository is a shallow clone
    When the developer runs /semantic-scan
    Then the scan exits with a non-zero code
    And the output reports the exact string: "Shallow clone detected — semantic-scan requires full history for incremental mode. Run with --full to override."

  Scenario: Register cannot be written due to file system permissions
    Given the project root directory is not writable by the current user
    When the developer runs /semantic-scan
    Then the scan exits with a non-zero code
    And the output reports the exact path that could not be written and the OS-level error

  Scenario: Semantic duplicate detected across inferred layers
    Given a source file in the domain layer containing a function that applies a percentage discount to a base price
    And a source file in the presentation layer containing a function that independently computes a discounted total using the same inputs
    When the developer runs /semantic-scan
    Then a duplicate cluster is reported containing both functions
    And the domain-layer function is identified as the suggested canonical in the format "canonical: suggested <file:line> — requires human confirmation"
    And the presentation-layer function is listed with its file:line reference

  Scenario: Canonical does not exist in any registered copy
    Given source files in three different layers each containing a function computing the same domain concept
    And all three functions import infrastructure-specific dependencies
    When the developer runs /semantic-scan
    Then a duplicate cluster is reported containing all three functions with their file:line references
    And the output includes "canonical: none — a new domain-layer implementation may be required"

  Scenario: No semantic duplicates detected
    Given all source files contain computations that express distinct domain concepts
    When the developer runs /semantic-scan
    Then no duplicate clusters are reported
    And the output confirms "No semantic duplication detected"

  Scenario: Scan scoped to a subdirectory — existing out-of-scope entries preserved
    Given computation-register.json exists with entries for files both inside and outside src/pricing
    When the developer runs /semantic-scan src/pricing
    Then only files under src/pricing are re-annotated in this pass
    And entries for files outside src/pricing are unchanged in the register
    And lastScanCommit is updated to HEAD

  Scenario: Scoped scan cluster includes out-of-scope entries — user is notified
    Given computation-register.json exists with entries for files inside and outside src/pricing
    And a duplicate cluster spans one entry in src/pricing and one entry outside src/pricing
    When the developer runs /semantic-scan src/pricing
    Then the duplicate cluster is reported
    And the output includes "Note: this cluster includes 1 entry outside the scoped path — run without scope argument to see full context"

  Scenario: Ignore configuration removes previously-registered entries
    Given computation-register.json exists with entries for files under src/legacy/
    And a .semanticscanignore file lists src/legacy/
    When the developer runs /semantic-scan
    Then files under src/legacy/ are not annotated
    And existing register entries for files under src/legacy/ are removed from the register

  Scenario: No computation units found in scope on first run
    Given no computation-register.json exists
    And no source files in scope contain non-trivial computations
    When the developer runs /semantic-scan
    Then no register is created
    And the output reports "No computation units found to analyze"

  Scenario: Incremental scan with changed files all trivial after pre-filter
    Given computation-register.json exists with entries from a prior scan
    And 3 source files have changed since lastScanCommit
    And all 3 changed files contain only trivial functions after pre-filter
    When the developer runs /semantic-scan
    Then no entries are added or modified in the register
    And the output reports "No new computation units found in changed files — register unchanged"

  Scenario: lastScanCommit not in git history
    Given computation-register.json records a lastScanCommit that no longer exists in history
    When the developer runs /semantic-scan
    Then the skill falls back to full-scan mode
    And the output warns "lastScanCommit not found in history — running full scan"
```

## Architecture Specification

### New Components

| Component | Location | Notes |
|-----------|----------|-------|
| Skill | `plugins/dev-team/skills/semantic-duplication-scan/SKILL.md` | Defines scan procedure |
| Command | `plugins/dev-team/commands/semantic-scan.md` | User-invocable entry point |
| Register | `computation-register.json` in user's project root | Created per-project, not shipped with plugin |

### Register Entry Schema

```json
{
  "file": "src/checkout/order-service.ts",
  "function": "applyDiscount",
  "layer": "domain",
  "semanticDescription": {
    "verb": "calculates",
    "domainConcept": "discounted price",
    "inputs": ["base price", "discount rate"],
    "outputConcept": "price after discount applied"
  },
  "promptVersion": "1.0",
  "commitHash": "abc123"
}
```

### Layer Inference Rules

| Coupling profile | Inferred layer |
|-----------------|---------------|
| Imports DB clients, ORMs, HTTP clients, message brokers | `infrastructure` |
| Imports rendering primitives, formats for display, accesses DOM/templates | `presentation` |
| Depends only on domain types and pure functions | `domain` |
| Orchestrates domain + infrastructure without owning rules | `application` |
| Cannot be determined from coupling profile | `unknown` |

### Process Flow

1. Mode detection — check for register; full if absent, incremental if present
2. Pre-flight — in incremental mode, check `git rev-parse --is-shallow-repository`; exit if shallow
3. Scope resolution — apply path argument, then `.semanticscanignore`
4. File selection — incremental: `git diff <lastScanCommit> HEAD --name-only`; full: glob all source files
5. Pre-filter — exclude test files, config, generated code, and trivial functions (no LLM call)
6. Annotation — batch files to LLM (Haiku, file-level): extract non-trivial computations with structured semantic descriptions and inferred layer; emit progress per file; collect failures in `scanErrors`
7. Register update — merge new entries, remove stale/ignored entries, sort for idempotency, update `lastScanCommit`
8. Clustering — shard by layer pair, Sonnet per shard; shard further by first domainConcept token if shard exceeds 50k tokens
9. Canonical suggestion — score by infrastructure coupling; escalate ambiguous clusters to Opus; output `canonical:` prefixed verdicts
10. Report — structured output per cluster with `file:line` references and cross-scope notices

### Model Routing

| Step | Model | Reason |
|------|-------|--------|
| Annotation + layer inference | Haiku | High volume, structured schema |
| Clustering | Sonnet | Cross-entry semantic grouping |
| Canonical scoring (ambiguous) | Opus | Judgment under uncertainty |

### Constraints

- Diagnostic only — no code changes suggested
- Canonical designations are always suggestions; human confirmation required
- Register lives in the user's project, not the plugin directory
- Shallow clone blocks incremental mode; `--full` overrides

## Acceptance Criteria

1. `computation-register.json` is valid JSON and human-readable
2. Idempotency: two runs with no code changes produce structurally identical register output (same entries, same semantic descriptions, same file:line references; `lastScanCommit` excluded from comparison)
3. Incremental mode never re-annotates files whose paths are not in `git diff <lastScanCommit> HEAD --name-only`
4. Functions containing no arithmetic operators, boolean logic, branching constructs, assignments to variables outside their own scope, or higher-order collection operations are absent from the register
5. Shallow clone in incremental mode exits non-zero and outputs the exact string: "Shallow clone detected — semantic-scan requires full history for incremental mode. Run with --full to override."
6. Exit code 0 on scan success regardless of whether duplicates were found; non-zero only on scan failure or pre-flight error
7. All report findings include `file:line` references pointing to the first line of the identified function
8. Every duplicate cluster report uses a consistent `canonical:` prefix: "canonical: suggested <file:line> — requires human confirmation" or "canonical: none — a new domain-layer implementation may be required"
9. Annotation failures are never silent: any file that could not be annotated is reported in a scan summary with the error reason, and the register includes a `scanErrors` array for that run

## Consistency Gate

- [x] Intent is unambiguous — trivial function, semantic description format, layer inference, and canonical-as-decision are all defined
- [x] Every behavior in the intent has at least one BDD scenario
- [x] Architecture constrains without over-engineering — no speculative features
- [x] Terminology is consistent across all four artifacts
- [x] No contradictions between artifacts
