# Plan: Semantic Duplication Scan

**Created**: 2026-05-11
**Branch**: main
**Status**: implemented

## Goal

Add a `/semantic-scan` skill and command that detects business logic reimplemented multiple times across architectural layers. The skill builds a persistent `computation-register.json` in the user's project, incrementally updated via `git diff`, and runs a clustering pass to surface semantic duplicates with `file:line` references. Canonical designation is always a suggestion requiring human confirmation. This addresses the gap where linters catch syntactic duplication and `domain-review` catches single-instance layer violations, but no existing tool detects the same domain calculation independently reimplemented in multiple layers.

## Acceptance Criteria

- [ ] `computation-register.json` is valid JSON and human-readable
- [ ] Idempotency: two runs with no code changes produce structurally identical register output (same entries, same semantic descriptions, same file:line references; `lastScanCommit` and `scanTimestamp` fields excluded from comparison)
- [ ] Incremental mode never re-annotates files whose paths are not in `git diff <lastScanCommit> HEAD --name-only`
- [ ] Functions containing no arithmetic operators, boolean logic, branching constructs, assignments to variables outside their own scope, or higher-order collection operations (map, filter, reduce) are absent from the register
- [ ] Shallow clone in incremental mode exits non-zero and outputs the exact string: "Shallow clone detected — semantic-scan requires full history for incremental mode. Run with --full to override."
- [ ] Exit code 0 on scan success regardless of whether duplicates were found; non-zero only on scan failure or pre-flight error
- [ ] All report findings include `file:line` references pointing to the first line of the identified function
- [ ] Every duplicate cluster report uses a consistent `canonical:` prefix: "canonical: suggested <file:line> — requires human confirmation" or "canonical: none — a new domain-layer implementation may be required"
- [ ] Annotation failures are never silent: any file that could not be annotated is reported in a scan summary with the error reason, and the register includes a `scanErrors` array for that run

## Performance Guidelines

Tracked as benchmarks in `evals/fixtures/sds-benchmark/`, not binary acceptance criteria.

- Incremental scan on ≤20 changed files: target under 90 seconds
- Full scan of the `sds-benchmark-500` fixture: target under 10 minutes
- False positive target: fewer than 20% of flagged clusters on the `sds-benchmark-500` fixture; ground truth determined by fixture annotations

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
    And functions containing no arithmetic, boolean logic, branching, external assignments, or higher-order collection operations are excluded
    And the developer sees progress output as each file is annotated: "Annotating [N/total] <filename>"

  Scenario: Annotation failure is reported, not silenced
    Given a full scan is running
    And annotation fails for one file due to a transient LLM error
    When the scan completes
    Then the register is written with all successfully annotated files
    And the register includes a scanErrors array identifying the failed file and error reason
    And the developer sees a warning: "Warning: 1 file could not be annotated. Re-run /semantic-scan to retry."
    And the scan exits with code 0 (partial success is not a failure)

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

## Steps

### Step 1: Scaffold skill with trivial-function definition and pre-filter rules

**Complexity**: standard
**RED**: Create eval fixture `evals/fixtures/sds-prefilter-trivial` — a source file containing only trivial functions (getters, pass-through delegators, identity functions, constructors that only assign parameters to fields). Expected output from skill: empty register, "No computation units found to analyze."
**GREEN**: Create `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md` with:
  - Frontmatter: `name`, `description`, `role: worker`, `user-invocable: true`
  - Overview section referencing the spec at `docs/specs/semantic-duplication-scan.md`
  - Trivial function definition: "A function is trivial if it contains no arithmetic operators (+, -, *, /, %, **), no boolean logic operators (&&, ||, !, not, and, or), no branching constructs (if, else, switch, ternary, match), no assignments to variables outside its own scope, and no calls to higher-order collection operations (map, filter, reduce, flatMap). Getters, pass-through delegators, identity functions, and constructors that only assign parameters to fields are trivial."
  - Pre-filter rules: exclude `*.test.*`, `*.spec.*`, `__tests__/`, `*.generated.*`, `*.pb.*`, `dist/`, `build/`, `.semanticscanignore` patterns, and trivial functions per definition. No LLM call at this stage.
**REFACTOR**: Verify definition is unambiguous across TypeScript, Python, and Go examples.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-prefilter-trivial`
**Commit**: `feat: add semantic-duplication-scan skill scaffold with pre-filter rules`

---

### Step 2: Add annotation procedure, register schema, and prompt versioning

**Complexity**: standard
**RED**: Create eval fixture `evals/fixtures/sds-annotation-schema` — a file with one non-trivial computation function. Expected output: a register entry with all required fields populated and valid, `promptVersion` present and non-empty.
**GREEN**: Add to SKILL.md:
  - Register entry schema with `promptVersion` field
  - `domainConcept` canonicalization: lowercase, strip articles (a, an, the), normalize verb to infinitive
  - Annotation prompt (pinned verbatim): "Describe only what this function computes in domain business terms using the JSON schema. Do not reference the implementation language, variable names, or data structure types. Use lowercase infinitive verbs."
  - Batching: one Haiku call per file; all non-trivial functions in a single call
  - Progress: emit "Annotating [N/total] \<filename\>" to stderr before each file's LLM call
  - Partial failure: if a file's LLM call fails, record `{file, error}` in `scanErrors` and continue; warn at end: "Warning: N files could not be annotated. Re-run /semantic-scan to retry."
  - `promptVersion` re-annotation: entries whose `promptVersion` differs from SKILL.md current version are treated as stale and re-annotated on the next scan pass that touches that file
**REFACTOR**: Confirm canonicalization produces stable output for phrasing variants of the same concept.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-annotation-schema`
**Commit**: `feat: add annotation procedure, register schema, and prompt versioning`

---

### Step 3: Add layer inference from coupling profile

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/sds-layer-infrastructure` — function importing `pg`, `redis`, `axios`; expected: `infrastructure`
  - `evals/fixtures/sds-layer-domain` — function with no external imports; expected: `domain`
  - `evals/fixtures/sds-layer-presentation` — function importing a React component; expected: `presentation`
  - `evals/fixtures/sds-layer-unknown` — function with ambiguous imports; expected: `unknown`
**GREEN**: Add layer inference table to SKILL.md annotation section (inferred in the same Haiku call):

  | Coupling profile | Inferred layer |
  |-----------------|---------------|
  | Imports DB clients, ORMs, HTTP clients, message brokers | `infrastructure` |
  | Imports rendering primitives, formats for display, accesses DOM/templates | `presentation` |
  | Depends only on domain types and pure functions, no external imports | `domain` |
  | Orchestrates domain + infrastructure without owning business rules | `application` |
  | Cannot be determined from coupling profile | `unknown` |

**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-layer-*`
**Commit**: `feat: add layer inference rules to annotation procedure`

---

### Step 4: Add mode detection, pre-flight checks, and --full flag

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/sds-shallow-clone` — register exists, shallow clone; expected: exit non-zero, exact error string
  - `evals/fixtures/sds-mode-full-no-register` — no register; expected: full-scan mode
  - `evals/fixtures/sds-mode-incremental` — register with valid `lastScanCommit`; expected: incremental mode
  - `evals/fixtures/sds-full-flag-override` — register exists, `--full` passed; expected: all files re-annotated
  - `evals/fixtures/sds-missing-commit` — `lastScanCommit` not in history; expected: fallback to full scan, warning emitted
  - `evals/fixtures/sds-permissions-failure` — project root not writable; expected: exit non-zero, path + OS error
**GREEN**: Add to SKILL.md:
  - Mode detection: full if no register, incremental if register present
  - Pre-flight (incremental only): `git rev-parse --is-shallow-repository`; if `true`, emit exact error string and exit non-zero
  - `--full` flag: skip shallow-clone check, force full-scan mode
  - Missing `lastScanCommit`: warn "lastScanCommit not found in history — running full scan" and fall back to full mode
  - Write-failure: if register cannot be written, emit path + OS error and exit non-zero
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-*`
**Commit**: `feat: add mode detection, pre-flight checks, and --full flag`

---

### Step 5: Add incremental scan, register update, and idempotency

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/sds-incremental-5-of-100` — 100 entries, 5 changed files; expected: 5 re-annotated, 95 unchanged, `lastScanCommit` updated
  - `evals/fixtures/sds-incremental-0-changed` — no files changed; expected: no entries modified, `lastScanCommit` updated, "No changes since last scan — register up to date"
  - `evals/fixtures/sds-incremental-deleted-file` — entry exists for a deleted file; expected: entry removed
  - `evals/fixtures/sds-idempotency` — two runs with identical source; expected: structurally identical register (excluding `lastScanCommit`)
**GREEN**: Add to SKILL.md:
  - File selection: `git diff <lastScanCommit> HEAD --name-only` filtered to source files in scope
  - Apply `.semanticscanignore` and pre-filter to the diff result
  - Deleted files: entries whose `file` path no longer exists are removed
  - Merge strategy: replace entries for re-annotated paths; preserve all others
  - Idempotency: sort register entries by `file` then `function` before writing; `domainConcept` canonicalization ensures consistent field values
  - `promptVersion` staleness: re-annotate any entry whose `promptVersion` differs from current on the next scan that touches that file
  - Update `lastScanCommit` to HEAD after successful write
**REFACTOR**: Verify sort order is stable across naming conventions.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-incremental-*`, `evals/fixtures/sds-idempotency`
**Commit**: `feat: add incremental scan, register update, and idempotency`

---

### Step 6a: Add clustering with register partitioning

**Complexity**: complex
**RED**: Create eval fixture `evals/fixtures/sds-no-duplicates` — register with 5 entries each with distinct canonicalized `domainConcept` values. Expected: no clusters, "No semantic duplication detected."
**GREEN**: Add clustering procedure to SKILL.md:
  - Partition strategy: shard register by layer pair (domain×presentation, domain×infrastructure, application×presentation) as separate Sonnet calls
  - Token budget: if a shard exceeds 50,000 tokens, further shard by first normalized token of `domainConcept`
  - Sonnet clustering prompt (pinned verbatim): "Group these entries by semantic equivalence — entries that compute the same domain concept regardless of implementation differences. Return clusters as JSON arrays of entry IDs. Two entries belong in the same cluster only if both would need to change if the underlying business rule changed."
  - Progress: emit "Clustering [layer-pair]: domain × presentation..." before each Sonnet call
  - Cross-shard reconciliation: after per-shard clustering, run a lightweight merge pass on cluster representatives to catch cross-shard equivalents, keeping the merge input under the 50k threshold
**REFACTOR**: Confirm shard boundaries don't suppress cross-shard duplicates.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-no-duplicates`
**Commit**: `feat: add clustering with register partitioning`

---

### Step 6b: Add canonical scoring and duplicate report

**Complexity**: complex
**RED**: Create eval fixture `evals/fixtures/sds-duplicate-with-canonical` — domain-layer `applyDiscount` (no infrastructure imports) and presentation-layer `computeFinalPrice` (imports render helper). Expected: duplicate cluster, domain entry as canonical in format "canonical: suggested \<file:line\> — requires human confirmation", cross-scope notice if applicable.
**GREEN**: Add to SKILL.md:
  - Canonical scoring: rank by layer (`domain` > `application` > `presentation` > `infrastructure` > `unknown`); within same layer, rank by count of infrastructure imports (fewer = higher rank)
  - Ambiguity predicate: if top two candidates tie on layer rank AND differ by ≤1 infrastructure import → escalate to Opus; emit "Resolving ambiguous canonical for cluster: \<domainConcept\>..."
  - Opus prompt: "Given these N entries computing the same domain concept, which is the most appropriate canonical location? Consider domain purity, reusability, and least coupling to delivery mechanism."
  - Output canonical:
    - Clear winner: "canonical: suggested \<file:line\> — requires human confirmation"
    - No winner: "canonical: none — a new domain-layer implementation may be required"
  - Cross-scope notice (scoped runs): "Note: this cluster includes N entry/entries outside the scoped path — run without scope argument to see full context" (use "entry" for N=1, "entries" for N>1)
  - `--no-opus` flag: skip Opus escalation; report ambiguous clusters as "canonical: ambiguous — human review required"
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-duplicate-with-canonical`
**Commit**: `feat: add canonical scoring and duplicate report`

---

### Step 6c: Add no-canonical handling and file:line accuracy

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/sds-no-canonical` — three infrastructure-coupled files computing the same concept. Expected: cluster with "canonical: none — a new domain-layer implementation may be required"
  - `evals/fixtures/sds-fileline-accuracy` — fixture with known function positions; expected: reported line numbers match first line of each function definition
**GREEN**: Add to SKILL.md:
  - `file:line` references point to the first line of the function definition (not the body)
  - If a file has changed since annotation, append staleness note: "(line may have shifted — re-run scan to refresh)"
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-no-canonical`, `evals/fixtures/sds-fileline-accuracy`
**Commit**: `feat: add no-canonical handling and file:line accuracy`

---

### Step 7: Add scoping, ignore configuration, and empty-scan handling

**Complexity**: standard
**RED**: Create eval fixtures:
  - `evals/fixtures/sds-subdirectory-scope` — register with entries inside and outside `src/pricing`; scan scoped to `src/pricing`. Expected: only `src/pricing` files re-annotated; out-of-scope entries unchanged
  - `evals/fixtures/sds-scoped-cross-scope-notice` — cluster spans `src/pricing` and `src/checkout`; scan scoped to `src/pricing`. Expected: cluster reported with cross-scope notice
  - `evals/fixtures/sds-semanticscanignore-removes-entries` — register with `src/legacy/` entries; `.semanticscanignore` lists `src/legacy/`. Expected: entries removed
  - `evals/fixtures/sds-empty-scope` — no register, all files trivial. Expected: "No computation units found to analyze", no register created
  - `evals/fixtures/sds-incremental-trivial-changed` — register exists, 3 changed files all trivial. Expected: "No new computation units found in changed files — register unchanged"
**GREEN**: Add to SKILL.md:
  - Subdirectory scoping: path argument as prefix filter; out-of-scope register entries preserved
  - `.semanticscanignore`: one glob per line; newly-ignored path entries removed from register on next scan
  - Empty scan (first run): "No computation units found to analyze"; register not created
  - Incremental trivial-changed: "No new computation units found in changed files — register unchanged"
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/skills/semantic-duplication-scan/SKILL.md`, `evals/fixtures/sds-*`
**Commit**: `feat: add scoping, ignore configuration, and empty-scan handling`

---

### Step 8: Create the command file

**Complexity**: trivial
**RED**: Confirm `/semantic-scan` is not discoverable without a command file (not listed in `/help` output).
**GREEN**: Create `plugins/agentic-dev-team/commands/semantic-scan.md` with frontmatter `argument-hint: "[path] [--full] [--no-opus]"` and body delegating to the skill.
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/commands/semantic-scan.md`
**Commit**: `feat: add /semantic-scan command entry point`

---

### Step 9: Update agent registry and CLAUDE.md quick reference

**Complexity**: trivial
**RED**: Run `/agent-audit` — expect structural compliance failures for missing registry entries.
**GREEN**:
  - Append to `knowledge/agent-registry.md` Skills Registry table: `| Semantic Duplication Scan | skills/semantic-duplication-scan/SKILL.md | ~TBD | Orchestrator, Software Engineer |`
  - Append to `plugins/agentic-dev-team/CLAUDE.md` Slash Commands table: `| /semantic-scan | commands/semantic-scan.md | worker | Build computation register and detect semantic duplicates across architectural layers |`
  - Update `~TBD` token count after Steps 1–8 are complete
**REFACTOR**: None needed.
**Files**: `plugins/agentic-dev-team/knowledge/agent-registry.md`, `plugins/agentic-dev-team/CLAUDE.md`
**Commit**: `docs: register semantic-scan skill and command in registry and CLAUDE.md`

---

## Complexity Classification

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Single-file rename, config change, typo fix, documentation-only | Skip inline review; covered by final `/code-review` |
| `standard` | New function, test, module, or behavioral change within existing patterns | Spec-compliance + relevant quality agents |
| `complex` | Architectural change, security-sensitive, cross-cutting concern, new abstraction | Full agent suite including opus-tier agents |

## Pre-PR Quality Gate

- [ ] All eval fixtures pass `/agent-eval`
- [ ] `/agent-audit` passes with no structural compliance failures
- [ ] `/code-review` passes on all new files
- [ ] SKILL.md token count estimated and added to registry entry
- [ ] CLAUDE.md quick reference updated
- [ ] `evals/fixtures/sds-benchmark/` fixture and README created for performance guideline tracking

## Risks & Open Questions

- **Clustering token budget**: Documented threshold (50,000 tokens per layer-pair shard). Fallback: shard further by `domainConcept` first token. Known limit, not a silent failure.
- **`promptVersion` drift**: Entries with old `promptVersion` are re-annotated on their next incremental scan pass. Full re-annotation required only if the `domainConcept` canonicalization rule changes.
- **Language coverage**: Trivial-function definition applied by Haiku at annotation time, reducing language-specific risk vs. AST-based approaches. Higher-order function patterns (map/filter/reduce) explicitly listed.
- **Register commit convention**: Committing recommended for team projects; `.gitignore` acceptable for solo. Neither enforced. SKILL.md will include guidance.
- **`scanErrors` lifecycle**: Cleared when the next scan successfully re-annotates the previously-failed files. `--full` clears all prior `scanErrors` by re-attempting every file in scope.
- **Renamed files**: Rename edge case (old-path entry removed, new-path entry created) not covered by a scenario in this slice. Tracked as a known gap for a follow-on.
- **Higher-order function classification**: `map`/`filter`/`reduce` chains are non-trivial; explicitly included in the trivial-function exclusion list.

## Plan Review Summary

Four reviewers ran across two revision cycles. All four passed on the final revision.

| Reviewer | Verdict | Top Finding |
|----------|---------|-------------|
| Acceptance Test Critic | **approve** | 9 AC criteria binary-verifiable; rename edge case known gap |
| Design & Architecture Critic | **approve** | Canonicalization routine should be single named function; promptVersion + sharding resolve blockers |
| UX Critic | **approve** | All blockers resolved: progress feedback, partial failure, cross-scope notice, canonical phrasing, --retry-failed removed |
| Strategic Critic | **approve** | Correct problem fit, clean reversibility, incremental delivery after steps 2 and 6 |
