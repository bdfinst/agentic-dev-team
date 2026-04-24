# Spec: `security-review` agent `rule_id` emission + unified-finding adapter

> **Source**: surfaced in `docs/rule-id-audit.md` as Finding #1 (blocker). The agent emits JSON without a `rule_id`, but the unified-finding envelope requires one. No adapter exists today to normalize agent output. Consequence: agent findings don't dedup against semgrep in the unified-finding stream, breaking the rules-vs-prompts policy's assumed pipeline.
>
> **Companion docs**: `docs/rule-id-audit.md`, `docs/rules-vs-prompts-policy.md`.
>
> **Sequencing**: strategic blocker on the `agentic-security-assessment` → `agentic-security-assessment` plugin rename. Item 5 must ship before Item 4 (rename).

## Intent Description

The `security-review` agent in `plugins/agentic-dev-team/agents/security-review.md` emits JSON findings in a schema that omits `rule_id`, but the unified-finding envelope at `plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json` requires `rule_id` (line 7) with format `^[a-z0-9_-]+(\.[a-z0-9_-]+)+$` (line 12). No adapter in `skills/static-analysis-integration/` normalizes agent output into the envelope today.

This is a **functional blocker**. `fp-reduction` dedups on `rule_id + metadata.source_ref hash` (`fp-reduction.md:57`). Without a rule_id on agent findings, dedup either never matches (two findings for one issue) or undefined (runtime error / silent drop). The rules-vs-prompts policy assumes rule_id consistency; it is not enforceable until this lands.

Fix: add a `category` field (required) to the agent output, ship a canonical **mapping table** (category → rule_id), build a thin **Python adapter** that reads agent JSON and emits unified-finding JSONL, and wire the adapter into Phase 1b of `/security-assessment`. Per rules-vs-prompts policy Q4 (adopt upstream rule_ids), the mapping emits the community/semgrep rule_id for classes where one exists; for judgment classes it emits `security-review.a<NN>.<slug>` (namespace already anticipated in `unified-finding-v1.json:13`'s example).

This slice unblocks dedup. It does NOT strip pattern-visible classes from `owasp-detection.md` — that is Item 3b, which lands after this.

## User-Facing Behavior

```gherkin
Feature: security-review agent findings normalize to unified-finding envelope

  Scenario: Category with community rule → upstream rule_id
    Given the security-review agent detects SQL injection
    And its JSON issue carries category "A03.sql-injection"
    When the adapter runs over the agent JSON
    Then the adapter emits a unified finding with rule_id == "semgrep.generic.sql-injection"
    And metadata.source == "security-review"
    And metadata.source_ref carries the original agent issue as an opaque pointer

  Scenario: Judgment-only category → security-review namespace
    Given the agent detects IDOR
    And its JSON issue carries category "A01.idor"
    When the adapter runs
    Then the adapter emits rule_id == "security-review.a01.idor"
    And the rule_id matches the unified-finding v1 regex ^[a-z0-9_-]+(\.[a-z0-9_-]+)+$

  Scenario: Rule_id case normalization (Q7)
    Given the agent emits category "A03.sql-injection" (uppercase A)
    When the adapter writes the rule_id
    Then the rule_id is lowercased to fit the envelope regex ^[a-z0-9_-]+(\.[a-z0-9_-]+)+$
    And no uppercase letter appears in any emitted rule_id

  Scenario: Cross-language rule_id format (Q1)
    Given the agent detects a pattern-visible class whose language is not disambiguated by file extension
    When the adapter maps to an upstream rule_id
    Then the adapter uses "semgrep.generic.<slug>" from the mapping table
    And for language-specific patterns the mapping emits "semgrep.<lang>.<slug>"

  Scenario: Dedup collapse with semgrep on the same issue
    Given semgrep emits rule_id "semgrep.generic.sql-injection" for api.py:42
    And the agent also detects the same issue at api.py:42 with category "A03.sql-injection"
    When both findings flow through fp-reduction
    Then dedup collapses them into one unified finding (identical rule_id)
    And the collapsed finding's locations array references both source_refs

  Scenario: Unknown category falls back to security-review namespace with warning
    Given the agent emits category "X99.experimental-class" not in the mapping table
    When the adapter runs
    Then a unified finding is emitted with rule_id == "security-review.x99.experimental-class"
    And stderr contains the line: "WARN: category X99.experimental-class not in mapping; minted security-review.x99.experimental-class"

  Scenario: Missing category field is a hard failure (Q5)
    Given the agent emits a JSON issue with no category field
    When the adapter runs
    Then the adapter exits non-zero
    And stderr contains: "ERROR: agent issue missing required 'category' field; upgrade the agent output"
    And no unified finding is emitted for that issue
    And the adapter's exit code is 1

  Scenario: Adapter output validates against the envelope schema
    Given the adapter has just emitted a unified finding
    When that finding is validated against plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json
    Then validation passes

  Scenario: Mapping table is the single source of truth
    Given the mapping table at plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml
    When the adapter resolves a category to a rule_id
    Then it reads only that YAML file
    And no inline mapping exists in the adapter source code
    And no inline mapping exists in agents/security-review.md

  Scenario: Mapping table has its own version (Q2)
    Given the mapping YAML declares `version: 1.0.0`
    When consumers read the mapping
    Then the version is a standalone field (not tied to the primitives-contract version)
    And bumping the mapping version does not require a primitives-contract bump

  Scenario: Backward compatibility with /code-review
    Given /code-review invokes the security-review agent without calling the adapter
    When the agent emits its JSON output (now with category field)
    Then /code-review's issue-list renderer continues to work
    And the new category field is additive (consumers that don't need rule_id ignore it)

  Scenario: Orchestrator-invoked adapter in Phase 1b (Q4, Q8)
    Given /security-assessment runs Phase 1b
    When the security-review agent emits findings
    Then the Phase 1b orchestrator explicitly invokes the adapter against the agent's output
    And memory/findings-<slug>.jsonl gains one unified finding per agent issue
    And every such finding carries rule_id, metadata.source == "security-review", and metadata.source_ref

  Scenario: owasp-detection.md patterns carry category IDs
    Given the agent reads owasp-detection.md before analysis
    Then every pattern row declares which category the agent should emit when that pattern matches
    And the categories follow the format A<NN>.<slug>
```

## Architecture Specification

### Components

| Component | Change |
| --------- | ------ |
| `plugins/agentic-dev-team/agents/security-review.md` | Add required `category` field to output JSON schema. Update prose to reference categories. |
| `plugins/agentic-dev-team/knowledge/owasp-detection.md` | Add category-ID column to each pattern table so the agent knows which category to emit. |
| `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` | **New.** Single source of truth: category → canonical `rule_id`. Initial coverage = 21 entries (11 upstream-mapped per policy + 10 judgment-only). |
| `plugins/agentic-dev-team/scripts/security-review-adapter.py` | **New.** Python adapter. Reads agent JSON, resolves categories via mapping, emits unified-finding JSONL. JSON Schema validation via `jsonschema` lib. |
| `plugins/agentic-dev-team/skills/static-analysis-integration/references/security-review-adapter.md` | **New.** Adapter documentation: invocation contract, error semantics, category format. |
| `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md` | One paragraph added under Tier 3 referencing the new adapter. |
| `plugins/agentic-security-assessment/skills/security-assessment-pipeline/SKILL.md` | Phase 1b documents mandatory adapter invocation after agent emission. |

### Category format

`A<NN>.<slug>` where:

- `A<NN>` is the OWASP top-10 category (zero-padded two digits, uppercase `A` in the agent output)
- `<slug>` is kebab-case vulnerability identifier

Examples: `A03.sql-injection`, `A01.missing-auth-middleware`, `A02.weak-hashing-md5`.

The adapter lowercases the `A<NN>` segment when building `security-review.*` rule_ids (Q7) to satisfy the unified-finding regex.

### Mapping table shape

File: `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml`

```yaml
version: 1.0.0
mappings:
  # Pattern-visible classes — adopt upstream rule_ids (policy Q4)
  A02.weak-hashing-md5: semgrep.generic.weak-hash-md5
  A03.sql-injection: semgrep.generic.sql-injection
  A03.xss-innerhtml: semgrep.javascript.xss-innerhtml
  A03.command-injection: semgrep.generic.command-injection
  A08.binary-formatter: semgrep.csharp.binary-formatter
  A08.object-input-stream: semgrep.java.deserialization-object-input-stream
  A08.js-eval: semgrep.javascript.eval-injection
  A05.cors-wildcard: semgrep.generic.cors-wildcard
  A07.jwt-alg-none: semgrep.generic.jwt-alg-none
  A02.insecure-random-js: semgrep.javascript.weak-random
  A05.default-credentials: semgrep.generic.default-credentials

  # Judgment-only classes — security-review namespace
  A01.idor: security-review.a01.idor
  A01.missing-auth-middleware: security-review.a01.missing-auth-middleware
  A01.missing-authorize-csharp: security-review.a01.missing-authorize-csharp
  A04.no-rate-limiting: security-review.a04.no-rate-limiting
  A04.no-brute-force-protection: security-review.a04.no-brute-force-protection
  A07.jwt-no-exp: security-review.a07.jwt-no-exp
  A07.session-fixation: security-review.a07.session-fixation
  A09.pii-in-logs: security-review.a09.pii-in-logs
  A05.verbose-errors-prod: security-review.a05.verbose-errors-prod
  A09.no-auth-event-logging: security-review.a09.no-auth-event-logging
```

### Agent output schema change (additive)

```json
{
  "status": "pass|warn|fail|skip",
  "issues": [{
    "category": "A<NN>.<slug>",
    "severity": "error|warning|suggestion",
    "confidence": "high|medium|none",
    "file": "",
    "line": 0,
    "message": "",
    "suggestedFix": ""
  }],
  "summary": ""
}
```

`category` is required on new emissions. Its regex: `^A[0-9]{2}\.[a-z0-9-]+$` (uppercase `A` in the internal agent output; lowercased by adapter on emission).

### Adapter contract

Language: **Python 3.10+** (Q3). Rationale: `jsonschema` library gives clean envelope validation; shell is reserved for hooks and lightweight glue.

Invocation:

```bash
security-review-adapter.py \
  --input agent-output.json \
  --output unified-findings.jsonl \
  [--mapping plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml]
```

Behavior:

- Reads one agent-output JSON from `--input` (not streaming; agent emits complete JSON per run)
- Iterates `issues[]`. For each issue:
  - If `category` missing: print ERROR to stderr, exit 1
  - If `category` found in mapping: emit unified finding with `rule_id = mapping[category]`
  - If `category` NOT in mapping: emit unified finding with `rule_id = "security-review." + lowercase(category)`; print WARN to stderr
  - Set `metadata.source = "security-review"`
  - Set `metadata.source_ref = <original agent issue>` (opaque)
  - Set `metadata.confidence = <issue.confidence>` (pass-through)
  - Copy `file`, `line`, `severity`, `message` verbatim
- Writes one JSONL line per emitted unified finding to `--output`
- Validates each emitted line against `unified-finding-v1.json` before writing. On validation failure: print ERROR to stderr, exit 1
- Exit 0 on success, 1 on any error

### Wiring

**`/code-review` (backward compat):**

The adapter is OPTIONAL. `/code-review`'s existing issue-list renderer continues to consume the agent's direct JSON output. Callsites that want unified findings explicitly invoke the adapter.

**`/security-assessment` Phase 1b (mandatory):**

The Phase 1b orchestrator (documented in `security-assessment-pipeline/SKILL.md`) invokes the adapter after the agent emits. Adapter output is appended to `memory/findings-<slug>.jsonl`. No agent-output-without-adapter path is accepted in Phase 1b.

### Single-source-of-truth invariant

Rule_ids live ONLY in `security-review-rule-map.yaml`. Neither the agent's prompt nor the adapter source code contains inline rule_id literals (beyond the hardcoded `"security-review."` prefix used for unknown-category fallback). Enforced by a unit test: `grep -rln 'semgrep\.\|security-review\.' plugins/agentic-dev-team/scripts/ plugins/agentic-dev-team/agents/security-review.md` returns zero rule_id-shaped matches outside the mapping table.

### Out of scope

- Stripping pattern-visible classes from `owasp-detection.md` (Item 3b)
- Primitives-contract version bump (the `security-review.*` namespace is already anticipated in the schema)
- Per-language rule_id differentiation beyond mapping-table entries
- Confidence-to-severity downgrade (exists in `fp-reduction`)
- Refactoring `/code-review` to use the adapter by default

## Acceptance Criteria

- [ ] AC-1: Agent output schema carries `category` as a required field; format regex `^A[0-9]{2}\.[a-z0-9-]+$` documented in `security-review.md`
- [ ] AC-2: `knowledge/security-review-rule-map.yaml` exists with ≥21 mappings; YAML parses; every rule_id value matches `^[a-z0-9_-]+(\.[a-z0-9_-]+)+$`
- [ ] AC-3: `scripts/security-review-adapter.py` exists and runs with the documented CLI
- [ ] AC-4: Adapter output validates against `unified-finding-v1.json` on positive fixtures
- [ ] AC-5: Positive fixture — `category: "A03.sql-injection"` → `rule_id: "semgrep.generic.sql-injection"` in emitted JSONL
- [ ] AC-6: Positive fixture — `category: "A01.idor"` → `rule_id: "security-review.a01.idor"`
- [ ] AC-7: Unknown-category fixture — `category: "X99.unknown"` → `rule_id: "security-review.x99.unknown"` with stderr WARN line
- [ ] AC-8: Missing-category fixture — adapter exits 1 with specific ERROR; no output line
- [ ] AC-9: Dedup fixture — semgrep `semgrep.generic.sql-injection` at `api.py:42` + agent `A03.sql-injection` at `api.py:42` → one unified finding after fp-reduction
- [ ] AC-10: Phase 1b wiring — `security-assessment-pipeline/SKILL.md` documents the adapter invocation; a smoke test runs the skill's documented flow against a fixture and verifies `memory/findings-<slug>.jsonl` has rule_ids on agent findings
- [ ] AC-11: `/code-review` backward compatibility — fixture run of `/code-review` on a code snippet produces the agent's JSON output with `category` field; no adapter invocation required
- [ ] AC-12: `owasp-detection.md` annotates every pattern row with its category ID
- [ ] AC-13: Single source of truth — `grep` for rule_id literals outside the mapping table returns empty
- [ ] AC-14: `static-analysis-integration/SKILL.md` Tier 3 section references `references/security-review-adapter.md`
- [ ] AC-15: Uppercase-to-lowercase case normalization — unit test confirms emitted rule_ids contain no uppercase letters

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts

**Gate: PASS (2026-04-24).** Proceeding to `/plan`.
