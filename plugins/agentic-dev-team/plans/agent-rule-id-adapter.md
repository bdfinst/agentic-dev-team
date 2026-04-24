# Plan: `security-review` agent `rule_id` emission + unified-finding adapter (Item 5)

**Created**: 2026-04-24
**Revised**: 2026-04-24 (post plan-review v1 — addresses 4 blockers)
**Approved**: 2026-04-24 (user approval; all four plan review personas approve v2)
**Branch**: main
**Status**: approved (v2)
**Spec**: `plugins/agentic-dev-team/docs/specs/agent-rule-id-adapter.md`
**Source**: Finding #1 of `docs/rule-id-audit.md` (functional blocker on dedup)
**Sequencing**: precedes Item 4 (plugin rename) per strategic review

## Goal

Close the `rule_id` emission gap for the `security-review` agent. The agent's output schema today omits `rule_id` (`security-review.md:10-14`), but the unified-finding envelope requires it (`unified-finding-v1.json:7`), and `fp-reduction` dedups on `rule_id + metadata.source_ref hash` (`fp-reduction.md:57`). Consequence: agent findings cannot dedup against semgrep findings, breaking the rules-vs-prompts policy's assumed pipeline.

Add a required `category` field to the agent output, ship a canonical YAML mapping table (category → rule_id), build a Python adapter that reads agent JSON and emits unified-finding JSONL, and wire the adapter into `/security-assessment` Phase 1b. Per policy Q4 (adopt upstream rule_ids), the mapping emits the community/semgrep `rule_id` where one exists; judgment-only classes get `security-review.a<NN>.<slug>` in the namespace already anticipated by the envelope schema.

Scope strictly limited to unblocking dedup. Does NOT strip pattern-visible classes from `owasp-detection.md` — that is Item 3b, which follows.

## Key decisions (resolved in v2)

1. **Adapter location.** Lives inside the static-analysis-integration skill at `plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py`, matching the pattern established by other per-source adapters (actionlint SARIF wrapper, tier-3 bespoke JSON adapters). One adapter tree; one maintainers list; one drift-CI job.
2. **Malformed category is a hard-fail, not a silent warning.** The LLM agent can emit drifted category strings (`A3.sqli`, `a03.sql-injection`, etc.). Silent-warn-and-continue would recreate the original dedup-blocker by minting `security-review.*` rule_ids that never collide with semgrep's. The adapter enforces `^A[0-9]{2}\.[a-z0-9-]+$` on incoming category; violations exit 1 with a specific ERROR. WARN is reserved for well-formed-but-unmapped categories (legitimate new classes not yet in the mapping).
3. **Step 4 annotates only judgment-only pattern rows in `owasp-detection.md`.** Pattern-visible rows are scheduled for removal in Item 3b; annotating them first would be thrown-away work. The agent emits `unknown-category` fallback for pattern-visible detections during the window between Step 4 and Item 3b — acceptable because those detections are the ones moving to semgrep rules anyway.

## Acceptance Criteria

From the spec (AC-1 … AC-15) plus three additions in v2 (AC-16 … AC-18) driven by the v1 plan review. Each step below closes one or more ACs.

- [ ] AC-1: Agent output schema carries `category` as a required field; format regex `^A[0-9]{2}\.[a-z0-9-]+$` documented in `security-review.md`
- [ ] AC-2: `knowledge/security-review-rule-map.yaml` exists with ≥21 mappings; YAML parses; every rule_id value matches `^[a-z0-9_-]+(\.[a-z0-9_-]+)+$`; a standalone top-level `version:` field is present and independent of the primitives-contract version
- [ ] AC-3: `skills/static-analysis-integration/adapters/security-review-adapter.py` exists and runs with the documented CLI
- [ ] AC-4: Adapter output validates against `unified-finding-v1.json` on positive fixtures
- [ ] AC-5: Positive fixture — `category: "A03.sql-injection"` → `rule_id: "semgrep.generic.sql-injection"`
- [ ] AC-6: Positive fixture — `category: "A01.idor"` → `rule_id: "security-review.a01.idor"`
- [ ] AC-7: Well-formed-but-unmapped category — `"A99.new-class"` → `rule_id: "security-review.a99.new-class"` with stderr WARN line including the mapping file path
- [ ] AC-8: Missing-category fixture — adapter exits 1 with specific ERROR; no output line
- [ ] AC-9: Dedup fixture — semgrep `semgrep.generic.sql-injection` at `api.py:42` + agent `A03.sql-injection` at `api.py:42` → one unified finding after fp-reduction's documented dedup key (adapter-side verification; end-to-end dedup tested in AC-10 runtime smoke)
- [ ] AC-10: **Runtime smoke test** — Phase 1b's documented flow is executed against a fixture; the adapter produces `memory/findings-fxt.jsonl` whose every line has non-empty `rule_id` and `metadata.source == "security-review"`
- [ ] AC-11: `/code-review` backward compatibility — raw agent JSON with the new `category` field preserves all fields the existing renderer consumes (`severity`, `file`, `line`, `message`, `suggestedFix`); `category` is verified additive via structural assertion
- [ ] AC-12: `owasp-detection.md` annotates every **judgment-only** pattern row with its category ID; pattern-visible rows are intentionally left unannotated (will be removed in Item 3b)
- [ ] AC-13: Single source of truth — AST-level test confirms no rule_id literal drives behavior in adapter Python source (excluding the `"security-review."` namespace prefix constant); pure grep is NOT the test of record — an AST walk over string literals filtered against the YAML's rule_ids is
- [ ] AC-14: `static-analysis-integration/SKILL.md` Tier 3 section references the adapter's new location
- [ ] AC-15: Uppercase-to-lowercase case normalization — unit test confirms emitted rule_ids contain no uppercase letters
- [ ] AC-16 (new): **Malformed category is a hard-fail.** Fixture with `category: "A3.sqli"` (regex-violating) → adapter exits 1 with `ERROR: category 'A3.sqli' does not match required format A<NN>.<slug>`
- [ ] AC-17 (new): **Language-specific rule_id emission.** Fixture with `category: "A03.xss-innerhtml"` → `rule_id: "semgrep.javascript.xss-innerhtml"`; confirms `<source>.<language>.<rule>` format is emitted correctly when the mapping declares it
- [ ] AC-18 (new): **Adapter self-documents mapping location.** Running `adapter.py --help` prints the default mapping path; module-level docstring names the YAML path and the spec file

## User-Facing Behavior

(Verbatim from spec; see `docs/specs/agent-rule-id-adapter.md` for the full set.)

```gherkin
Feature: security-review agent findings normalize to unified-finding envelope

  Scenario: Category with community rule → upstream rule_id
    Given the security-review agent detects SQL injection with category "A03.sql-injection"
    When the adapter runs
    Then a unified finding is emitted with rule_id "semgrep.generic.sql-injection"
    And metadata.source == "security-review"
    And metadata.source_ref deep-equals the original agent issue (verified by byte-for-byte JSON comparison)

  Scenario: Language-specific upstream rule_id (AC-17)
    Given category "A03.xss-innerhtml"
    Then rule_id == "semgrep.javascript.xss-innerhtml"

  Scenario: Judgment-only category → security-review namespace
    Given category "A01.idor"
    Then rule_id == "security-review.a01.idor"

  Scenario: Rule_id case normalization
    Given category "A03.sql-injection" (uppercase A)
    Then no uppercase letter appears in any emitted rule_id

  Scenario: Well-formed-but-unmapped category falls back to security-review namespace
    Given category "A99.new-class" (not in mapping but regex-valid)
    Then rule_id == "security-review.a99.new-class"
    And stderr contains: "WARN: category A99.new-class not in mapping at plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml; minted security-review.a99.new-class"

  Scenario: Malformed category is a hard failure (AC-16 — LLM drift guard)
    Given category "A3.sqli" (regex-violating — missing leading zero, malformed slug)
    Then the adapter exits 1
    And stderr contains: "ERROR: category 'A3.sqli' does not match required format A<NN>.<slug>"
    And no unified finding is emitted

  Scenario: Missing category field is a hard failure
    Given an agent issue without a category field
    Then the adapter exits 1
    And stderr contains: "ERROR: agent issue missing required 'category' field; upgrade the agent output"

  Scenario: Malformed mapping YAML is a hard failure
    Given the mapping YAML is syntactically invalid or missing the 'mappings' key
    Then the adapter exits 1
    And stderr contains: "ERROR: mapping file at <path> is invalid"

  Scenario: Emitted finding violating unified-finding schema is a hard failure
    Given the adapter is forced to emit a finding with a null or missing required field
    Then the adapter exits 1
    And stderr contains: "ERROR: emitted finding violates unified-finding-v1 schema"

  Scenario: Adapter output validates against the envelope schema
    Then every emitted JSONL line validates against unified-finding-v1.json

  Scenario: Dedup collapse with semgrep on the same issue (adapter-side)
    Given semgrep emits rule_id "semgrep.generic.sql-injection" for api.py:42
    And the agent emits category "A03.sql-injection" for api.py:42
    Then the two findings carry identical rule_ids in the unified stream
    And fp-reduction's documented dedup key collapses them into one unified finding

  Scenario: Runtime Phase 1b smoke (AC-10)
    Given a fixture agent-output.json with at least one mapped and one unmapped category
    When the Phase 1b documented invocation runs the adapter against it
    Then memory/findings-fxt.jsonl is written
    And every line has non-empty rule_id, metadata.source == "security-review"

  Scenario: Mapping table is the single source of truth
    Then no inline rule_id literal drives behavior in the adapter source code
    And no inline rule_id mapping exists in agents/security-review.md
    And the adapter module docstring names the YAML path and the spec file

  Scenario: Mapping table has its own version
    Then the YAML declares a top-level `version:` field
    And the version is independent of primitives-contract version

  Scenario: Backward compatibility with /code-review
    Given the agent emits JSON with the new `category` field
    Then every field /code-review's existing renderer consumes remains present and unchanged
    And the `category` field is additive — downstream that ignores it works

  Scenario: owasp-detection.md judgment-only patterns carry category IDs
    Then every judgment-only pattern row in owasp-detection.md declares its category ID
    And pattern-visible rows remain unannotated pending Item 3b

  Scenario: Adapter self-documents mapping location (AC-18)
    When the user runs `adapter.py --help`
    Then the output names the default mapping file path
    And the adapter module docstring names the YAML path and the spec file
```

## Steps

### Step 1: Foundation — mapping table + adapter skeleton + positive-case tests including language-specific

**Complexity**: complex

Establishes the single source of truth and the adapter's core shape. Everything downstream depends on this.

**RED**:

- Create `evals/security-review-adapter/fixtures/` directory.
- Create three positive-case input fixtures:
  - `agent-output-sql-injection.json` with `category: "A03.sql-injection"` (upstream-generic mapping)
  - `agent-output-xss-innerhtml.json` with `category: "A03.xss-innerhtml"` (upstream-language-specific mapping — closes AC-17)
  - `agent-output-idor.json` with `category: "A01.idor"` (judgment-namespace mapping)
- Create three expected-output fixtures as hand-authored `.jsonl` files:
  - `expected-unified-sql-injection.jsonl` with `rule_id: "semgrep.generic.sql-injection"`, metadata populated
  - `expected-unified-xss-innerhtml.jsonl` with `rule_id: "semgrep.javascript.xss-innerhtml"`
  - `expected-unified-idor.jsonl` with `rule_id: "security-review.a01.idor"`
- Create `evals/security-review-adapter/tests/test_mapping_table.sh`:
  - Assert `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` exists
  - Assert `python3 -c "import yaml; d = yaml.safe_load(open('plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml')); assert d['version'].count('.') == 2; assert len(d['mappings']) >= 21; [re.fullmatch(r'^[a-z0-9_-]+(\.[a-z0-9_-]+)+$', v) for v in d['mappings'].values()]"` passes
  - Assert the `version:` field is a standalone top-level key, not nested inside `mappings:`
- Create `evals/security-review-adapter/tests/test_adapter_positive.sh`:
  - For each of the three positive fixtures, invoke `python plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py --input <fixture> --output <tmp>`
  - Deep-equal `<tmp>` against `expected-unified-*.jsonl` EXCEPT that `metadata.source_ref` is validated specifically: assert `jq '.metadata.source_ref'` of the emitted line `== jq '.issues[0]'` of the input (proves source_ref is an opaque, byte-faithful copy of the input issue — closes the opacity-assertion blocker)
  - Covers upstream-generic (A03.sql-injection), upstream-language-specific (A03.xss-innerhtml), and judgment-namespace (A01.idor) cases
- Run both tests pre-change. All fail (mapping YAML absent, adapter absent).

**GREEN**:

- Create `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` with ≥21 entries. Include a top-level `version: 1.0.0` field. Include at least one language-specific mapping (e.g., `A03.xss-innerhtml: semgrep.javascript.xss-innerhtml`).
- Create `plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py`:
  - Module-level docstring names the YAML path AND the spec file (addresses AC-18)
  - CLI with `--input`, `--output`, `--mapping` (default points to the YAML); `--help` output names the default mapping path (AC-18)
  - Reads input JSON; iterates `issues[]`
  - For each issue: looks up `category` in mapping; emits unified-finding JSONL line
  - Happy path only at this step: mapped categories → unified finding with `rule_id` from mapping
  - Sets `metadata.source = "security-review"`, `metadata.source_ref = <original issue>` (byte-faithful opaque copy), `metadata.confidence = <issue.confidence>`
- Run tests. All pass.

**REFACTOR**: None at this step.
**Files**: `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` (new), `plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py` (new), six fixture files (three input + three expected), two test scripts (new)
**Commit**: `feat(security-review): canonical rule_id mapping + adapter happy-path (language-specific included)`

### Step 2: Error paths — malformed category hard-fail, well-formed-but-unmapped fallback, missing category hard-fail, malformed mapping YAML hard-fail

**Complexity**: standard

**RED**:

- Create fixtures:
  - `agent-output-malformed-category.json` with `category: "A3.sqli"` (regex-violating — closes UX blocker, AC-16)
  - `agent-output-unmapped-category.json` with `category: "A99.new-class"` (regex-valid but not in mapping)
  - `agent-output-missing-category.json` with an issue lacking `category` (AC-8)
  - `malformed-mapping.yaml` (syntactically broken YAML; test copies it into a tmp path and passes `--mapping <tmp>`)
- Create tests:
  - `test_adapter_malformed_category.sh`: run adapter on malformed-category fixture; assert exit 1; assert stderr contains `ERROR: category 'A3.sqli' does not match required format A<NN>.<slug>`; assert output file is empty
  - `test_adapter_unmapped_category.sh`: run adapter on unmapped-category fixture; assert exit 0; assert emitted `rule_id == "security-review.a99.new-class"`; assert stderr contains `WARN: category A99.new-class not in mapping at plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml; minted security-review.a99.new-class`
  - `test_adapter_missing_category.sh`: assert exit 1 + `ERROR: agent issue missing required 'category' field; upgrade the agent output`
  - `test_adapter_malformed_mapping.sh`: assert exit 1 + `ERROR: mapping file at <tmp path> is invalid`
- Run pre-change. All four fail.

**GREEN**:

- Extend adapter:
  - Before lookup, validate `category` against `^A[0-9]{2}\.[a-z0-9-]+$`. Violation → ERROR to stderr, exit 1 (AC-16)
  - Well-formed-but-unmapped: build `security-review.<lowercase(category)>`; print WARN to stderr (including mapping file path); emit finding
  - Missing `category` field: ERROR to stderr, exit 1 before any output
  - Mapping YAML load errors (FileNotFoundError, YAMLError, missing `mappings` key): ERROR with the mapping file path, exit 1
- Run tests. Pass.

**REFACTOR**: Extract `resolve_rule_id(category, mapping) -> (rule_id, warning_or_none)` if the conditional gets tangled.
**Files**: adapter (updated), four fixtures (new), four test scripts (new)
**Commit**: `feat(security-review): adapter error paths — malformed/unmapped category + missing category + bad mapping YAML`

### Step 3: Envelope schema validation + case normalization + negative schema fixture

**Complexity**: standard

**RED**:

- Create fixtures:
  - `agent-output-mixed-case.json` with `category: "A03.sql-injection"` (uppercase `A` internal)
  - `agent-output-forces-null-file.json` designed to produce a schema-invalid unified finding (e.g., `file: null` or missing `line`) — exercises Step 3's negative-validation gate
- Create tests:
  - `test_adapter_schema_valid.sh`: for every positive fixture, run adapter; validate each emitted JSONL line against `plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json` via `python -m jsonschema -i <line> <schema>` or the `jsonschema` library; assert all pass
  - `test_case_normalization.sh`: run adapter on mixed-case fixture; grep emitted rule_ids for `[A-Z]`; assert zero matches
  - `test_adapter_schema_violation_fixture.sh`: run adapter on `agent-output-forces-null-file.json`; assert exit 1 + stderr contains `ERROR: emitted finding violates unified-finding-v1 schema`
- Run pre-change. Tests fail.

**GREEN**:

- Integrate `jsonschema` library into the adapter. Validate each finding before writing; on failure, exit 1 with specific ERROR.
- Lowercase the category segment when building `security-review.*` rule_ids.
- Run tests. Pass.

**REFACTOR**: Load the schema once at adapter startup (not per-finding).
**Files**: adapter (updated), two fixtures (new), three test scripts (new)
**Commit**: `feat(security-review): adapter validates envelope schema + normalizes rule_id case + negative schema fixture`

### Step 4: Agent output schema + `owasp-detection.md` judgment-only category annotations + small reliability eval

**Complexity**: standard

**RED**:

- Create `test_agent_schema.sh`:
  - Awk-locate the "Output JSON:" code block in `agents/security-review.md`; assert it contains `category` as a required field on `issues[]`
  - Assert the agent doc documents the category regex `^A[0-9]{2}\.[a-z0-9-]+$` in prose
- Create `test_owasp_detection_judgment_categories.sh`:
  - Awk-parse `knowledge/owasp-detection.md`
  - For every row under a heading that names a **judgment-only** category (list derived from `knowledge/security-review-rule-map.yaml`'s `security-review.*` entries), assert a category ID cell is present matching `A[0-9]{2}\.[a-z0-9-]+`
  - Pattern-visible rows are allowed to be unannotated (will be removed in Item 3b)
- Create `test_category_emission_reliability.sh`:
  - A small reliability eval — 3-5 representative code fixtures paired with expected category emissions
  - Runs the agent (or uses canned output for CI determinism) against each fixture
  - Asserts the emitted category matches the expected one in ≥80% of cases (provisional floor)
  - Documents the failure list for follow-up prompt tightening
- Run pre-change. All three tests fail.

**GREEN**:

- Edit `plugins/agentic-dev-team/agents/security-review.md`:
  - Add `category` to the output JSON schema block as a required field on each issue
  - Add one paragraph documenting the category regex and pointing at `owasp-detection.md` for the canonical list
  - Add 2-3 concrete in-prompt examples of category emission (helps LLM reliability)
- Edit `plugins/agentic-dev-team/knowledge/owasp-detection.md`:
  - Add a `Category` column to every **judgment-only** row (IDOR, missing-auth-middleware, no-rate-limiting, session fixation, etc.)
  - Leave pattern-visible rows unannotated with a header comment: "Pattern-visible classes are detected by semgrep rules; category annotations will land alongside row removal in Item 3b."
- Author the 3-5 reliability-eval fixtures. Use canned agent output in CI to keep the test deterministic; a separate manual-eval mode can exercise the real agent.
- Run tests. Pass.

**REFACTOR**: None.
**Files**: `agents/security-review.md` (updated), `knowledge/owasp-detection.md` (updated), reliability-eval fixtures + harness (new), three test scripts (new)
**Commit**: `feat(security-review): agent output schema + judgment-only OWASP category annotations + reliability eval`

### Step 5: Dedup collapse verification — adapter side only (scope note)

**Complexity**: standard

**Scope note**: this step verifies the adapter emits rule_ids that fp-reduction's documented dedup algorithm collapses. It does NOT invoke fp-reduction itself. End-to-end Phase-1b dedup is covered by AC-10's runtime smoke test in Step 6. R6 is updated to reflect this split.

**RED**:

- Create fixtures:
  - `dedup-semgrep.jsonl` — one line: `{"rule_id": "semgrep.generic.sql-injection", "file": "api.py", "line": 42, "severity": "error", "message": "SQL injection", "metadata": {"source": "semgrep", "confidence": "high"}}`
  - `dedup-agent-output.json` — issue at `api.py:42` with `category: "A03.sql-injection"`
- Create `test_dedup_adapter_side.sh`:
  - Run adapter on agent fixture → `dedup-agent-unified.jsonl`
  - Assert the agent's emitted `rule_id == "semgrep.generic.sql-injection"` (matches semgrep's)
  - Concatenate both JSONLs; apply the fp-reduction dedup key algorithm (replicated from `fp-reduction.md:57` in a small Python helper — the helper IMPORTS the canonical dedup function if one is factored out; else replicates the key logic verbatim with a comment citing the source line)
  - Assert the post-dedup set has exactly 1 finding; surviving rule_id is `semgrep.generic.sql-injection`
- Run pre-change. Test fails (no adapter output yet, but adapter lands in Step 1 so by the time this runs the failure mode is different — the dedup helper may not exist).

**GREEN**:

- Verify adapter output already yields the correct rule_id (work done in Steps 1-3; nothing new in the adapter).
- Create the dedup helper script if not factored into fp-reduction. Prefer factoring: if fp-reduction.md's dedup can be extracted into `plugins/agentic-security-review/scripts/fp-reduction-dedup.py` (or equivalent), the helper imports it; else the helper replicates with a `# SOURCE: fp-reduction.md:57` comment tying it to the original.
- Run test. Pass.

**REFACTOR**: If the dedup algorithm is replicated, file an open item to factor it into fp-reduction proper.
**Files**: dedup fixtures (new), `test_dedup_adapter_side.sh` (new), optional `fp-reduction-dedup.py` helper (new if extraction path taken)
**Commit**: `test(security-review): adapter-side dedup verification — agent + semgrep collapse`

### Step 6: Skill wiring + AST-level single-source-of-truth + runtime Phase 1b smoke test + /code-review backward compat

**Complexity**: standard

**RED**:

- Create `test_skill_wiring.sh`:
  - Awk-check on `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md`: Tier 3 section references `adapters/security-review-adapter.py` at the new path
  - Awk-check on `plugins/agentic-security-review/skills/security-assessment-pipeline/SKILL.md` Phase 1b block: references the adapter invocation with the adapter's full new path
- Create `test_runtime_phase_1b_smoke.sh` (closes AC-10 blocker):
  - Stage a fake agent-output.json under a tmp memory/ dir with two issues: one mapped category, one unmapped
  - Execute the Phase 1b invocation verbatim as documented in `security-assessment-pipeline/SKILL.md`: `python <adapter-path> --input <fake> --output memory/findings-fxt.jsonl`
  - Assert `memory/findings-fxt.jsonl` exists and has exactly 2 lines
  - For each line, assert `jq -e '.rule_id != ""'` and `jq -e '.metadata.source == "security-review"'`
- Create `test_single_source_of_truth_ast.sh` (AST-level, addresses design warning on grep brittleness):
  - Parse the adapter Python source via the `ast` module
  - Walk all `ast.Constant` string-literal nodes
  - Load the mapping YAML; collect the set of rule_ids
  - Assert no string literal in the adapter source equals any mapping rule_id, EXCEPT the `"security-review."` prefix constant used in the fallback path
  - Assert no string literal matches the pattern `^semgrep\.` (guards against inline upstream rule_id literals)
  - This is a ~20-line Python test; far more robust than the v1 grep approach
- Create `test_code_review_backward_compat.sh` (strengthens AC-11 per acceptance warning):
  - Use a fixture `agent-output-backward-compat.json` with `category` plus all pre-existing fields
  - Assert via jq-equality that every field `/code-review`'s renderer consumes (`severity`, `file`, `line`, `message`, `suggestedFix`, `status`, `summary`) is present AND has the expected shape
  - Assert `category` is the only additive field at the `issues[]` level
- Run pre-change. All four tests fail.

**GREEN**:

- Edit `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md`:
  - Add one paragraph under Tier 3: "A thin adapter normalizes `security-review` agent output into the unified-finding envelope. See `adapters/security-review-adapter.py` and `references/security-review-adapter.md`."
- Create `plugins/agentic-dev-team/skills/static-analysis-integration/references/security-review-adapter.md`:
  - Document the adapter's CLI, input/output contracts, error semantics, failure modes, and mapping-table location
  - Include a "grep recipe" section documenting the uppercase-to-lowercase case translation so auditors know to grep both `A03` (agent side) and `a03` (unified-stream side)
- Edit `plugins/agentic-security-review/skills/security-assessment-pipeline/SKILL.md`:
  - In the Phase 1b block, append: "The `security-review` agent's output is piped through `plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py` before findings append to `memory/findings-<slug>.jsonl`. The adapter is mandatory in this phase; a non-zero exit halts Phase 1b with a named error."
- Ensure no inline rule_id literals in adapter source beyond the `"security-review."` prefix.
- Run all four tests. Pass.

**REFACTOR**: None.
**Files**: `static-analysis-integration/SKILL.md` (updated), `references/security-review-adapter.md` (new), `security-assessment-pipeline/SKILL.md` (updated), four test scripts (new)
**Commit**: `docs(security-review): adapter docs + Phase 1b wiring + AST invariant + runtime smoke + backward-compat`

## Complexity Classification

| Step | Rating   | Rationale |
| ---- | -------- | --------- |
| 1    | complex  | Foundation: mapping + adapter + three positive fixtures (including language-specific) + opacity assertion |
| 2    | standard | Four error-path additions — malformed category hard-fail (LLM drift guard), unmapped WARN, missing category, malformed YAML |
| 3    | standard | Schema validation (positive + negative fixture) + case normalization |
| 4    | standard | Agent output schema + judgment-only row annotation + small reliability eval |
| 5    | standard | Adapter-side dedup verification; end-to-end deferred to AC-10 in Step 6 |
| 6    | complex  | Skill wiring + AST-level invariant + runtime Phase 1b smoke + strengthened backward-compat |

## Pre-PR Quality Gate

- [ ] All `evals/security-review-adapter/tests/*.sh` pass
- [ ] `python -m jsonschema` validates every adapter-emitted line against `unified-finding-v1.json`
- [ ] Reliability eval (Step 4) reports ≥80% category-emission accuracy on the fixture set
- [ ] AST-level single-source-of-truth test reports no rule_id literal in adapter source beyond the prefix constant
- [ ] `/code-review` passes on the diff
- [ ] Manual: run adapter on a real `/code-review` agent invocation's JSON output against a realistic code sample; inspect rule_ids for sanity
- [ ] Manual: confirm Python adapter works with a clean `pip install jsonschema pyyaml`
- [ ] `docs/rule-id-audit.md` updated: Finding #1 marked as resolved
- [ ] `docs/rules-vs-prompts-policy.md`: remove the "advisory until Item 5 lands" caveat

## Risks & Open Questions

| # | Type | Item | Mitigation / Owner |
| - | ---- | ---- | ------------------ |
| R1 | Risk | Python + `jsonschema` + `pyyaml` dependency. Dev-team plugin doesn't require Python runtime otherwise. | Companion plugin already requires Python 3.10 for red-team harness; adapter reuses it. Document in Step 6's `references/security-review-adapter.md`. |
| R2 | Risk | LLM agent reliability of category emission — addressed in v2 by (a) adding malformed-category hard-fail (AC-16) and (b) a 3-5 case reliability eval with ≥80% floor in Step 4's GREEN. Hard-fail on regex violation prevents silent drift; the eval provides an observable accuracy bound. | Baked into v2. If ≥80% is not met, block Step 4 until prompt examples are tightened. |
| R3 | Open | The mapping table's initial 11 upstream rule_ids may not match actual semgrep rule_ids for `p/security-audit`. | Step 1 GREEN verifies via `semgrep --config p/security-audit --dump-rule-ids` or equivalent. |
| R4 | Resolved (v2) | `/code-review` backward compat now verified via explicit field-preservation jq assertions rather than bare `.message` presence. | Closed. |
| R5 | Open | `source_ref` shape — opacity now asserted via deep-equality (Step 1 v2). Downstream consumers still treat it as opaque. | Resolved for adapter output; downstream-treat-as-opaque confirmed by grep of `fp-reduction.md`. |
| R6 | Open → partial | End-to-end Phase 1b dedup is exercised by the runtime smoke test (AC-10 in Step 6) but the smoke does not run fp-reduction itself. True end-to-end verification (adapter → fp-reduction → collapsed output) is a follow-up. | File as follow-up tied to a later slice; acceptable because AC-9 (adapter-side) + AC-10 (runtime smoke) together close the observable gap. |
| R7 | Open (follow-up) | Post-merge: expand reliability eval to broader category coverage (≥15 cases). Raise the floor to 90% once the prompt is hardened. | Scheduled post-Item-5. |
| R8 | Open | Item 3b (strip pattern-visible classes from `owasp-detection.md`) is unblocked by this slice. v2 scoped Step 4 to judgment-only rows so pattern-row annotations aren't written just to be deleted by 3b. | 3b lands next; unannotated pattern rows emit unknown-category fallback in the interim (acceptable because they are precisely the rows moving to semgrep rules). |

## Plan Review Summary

Four personas ran in parallel against v1.

### Verdicts

| Reviewer | Verdict | Notes |
|---|---|---|
| Acceptance Test Critic | needs-revision (3 blockers) | AC-10 smoke test doc-only; source_ref opacity skipped not asserted; language-specific rule_ids untested |
| Design & Architecture Critic | approve with warnings | adapter location; grep brittleness; dedup simulates not invokes |
| UX Critic | needs-revision (1 blocker) | silent-warn on LLM-drifted categories recreates the original dedup-blocker |
| Strategic Critic | approve with warnings | reliability floor needed; dedup simulation scope note; Step 4 rewrite risk with Item 3b |

### Blockers resolved in v2

| Reviewer | Blocker | Resolution |
|---|---|---|
| Acceptance | AC-10 runtime smoke missing | Step 6 adds `test_runtime_phase_1b_smoke.sh` — executes the Phase 1b invocation verbatim against a fixture; asserts `memory/findings-fxt.jsonl` has rule_ids and correct source |
| Acceptance | source_ref opacity skipped in diff | Step 1 test now deep-equals `jq '.metadata.source_ref'` of emitted line vs `jq '.issues[0]'` of input — byte-faithful opacity verified by construction |
| Acceptance | Language-specific rule_id uncovered | Step 1 adds third positive fixture `A03.xss-innerhtml` → `semgrep.javascript.xss-innerhtml`, plus new AC-17 |
| UX | Silent-warn on malformed categories recreates dedup-blocker | New AC-16: malformed category (regex-violating) is a hard-fail with specific ERROR. WARN reserved for well-formed-but-unmapped categories only. Step 2 RED has `A3.sqli` fixture and assertion. |

### Design + Strategic warnings also adopted in v2 (not blockers, but free wins)

- Adapter location moved from `scripts/` to `skills/static-analysis-integration/adapters/` — matches established pattern for per-source adapters
- Single-source-of-truth test upgraded from raw grep to an AST-level walk of Python string literals compared against the YAML's rule_id set — far less brittle
- Step 4 annotation restricted to judgment-only rows in `owasp-detection.md`; pattern-visible rows left unannotated pending Item 3b removal (avoids rework)
- Step 5 explicitly scoped as adapter-side verification; end-to-end dedup closure is AC-10 in Step 6
- New AC-18 for adapter self-documentation (module docstring + `--help` names the mapping path)

### Residual warnings not addressed

- Error message UX: WARN/ERROR include the mapping file path per Step 2 GREEN (adopted)
- Step 5 replication-vs-import of fp-reduction dedup algorithm — v2 GREEN prefers factoring via an imported helper if one exists; otherwise replicates with a source-citing comment. True end-to-end dedup remains a follow-up (R6)
- Reliability eval size is 3-5 cases at 80% floor — strategic noted this is provisional. R7 tracks post-merge expansion

### Observations

- Mapping YAML as single source of truth with its own `version:` field correctly decouples rule-id catalog evolution from primitives-contract SemVer
- Uppercase-internal / lowercase-at-emission split is awkward in isolation but contained to one adapter boundary
- Cross-plugin Python dependency acceptable because companion plugin already owns the runtime
- Scope discipline strong — Item 3b, plugin rename, and contract bump explicitly deferred
