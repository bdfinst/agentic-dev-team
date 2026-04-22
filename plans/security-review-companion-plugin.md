# Plan: Security Review Companion Plugin + Reusable Primitives

**Created**: 2026-04-20
**Branch**: main
**Status**: approved (revision 7)
**Execution coordinator**: [`plans/combined-plan-opus-4-7-security-review.md`](./combined-plan-opus-4-7-security-review.md)

## Goal

Deliver deep-security-assessment and adversarial ML red-team capability inspired by `opus_repo_scan_test`, **inverting its prompt-heavy design**: deterministic tools do the detection, hooks automate invocation in the security plugin only, and LLM agents are reserved for semantic reasoning (business logic, narrative annotation, executive prose, cross-repo attack chains). Two plugins:

- **A. `agentic-dev-team`** receives reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned primitives contract, SARIF-first tool orchestration).
- **B. `agentic-security-review`** (new, mirrored layout + `harness/` extension) hosts: the PostToolUse auto-scan hook (default on, security-plugin-only), FP-reduction (joern + LLM with fallback banner), narrowly-LLM agents, `/security-assessment` orchestration, service-communication diagram tool, `/cross-repo-analysis`, compliance mapping (pattern-table first), PDF export, and the adversarial ML red-team harness (self-owned targets only).

## Plugin Structure Contract

`plugins/agentic-security-review/` mirrors `plugins/agentic-dev-team/` one-for-one; `harness/` is a first-class top-level directory for executable application code. Structural parity rule: "same schema where the directory applies; omitted directories documented in CLAUDE.md with rationale."

## Tool Orchestration Strategy (Decision Record)

**Decision:** SARIF-first. Only tools that emit SARIF (or that we can convert with a thin adapter) are first-class integrations. The unified finding schema is a narrow normalization over SARIF's `result` object.

**Why SARIF:**
- OASIS-standardized JSON schema; stable
- Already emitted by most modern security tools (semgrep, trivy, gitleaks, checkov, bandit, gosec, hadolint, actionlint, kube-linter, bearer, osv-scanner, grype)
- Free downstream integration (GitHub code scanning, VS Code SARIF viewer, SonarQube)
- Eliminates ~70% of bespoke parser maintenance

**Consequence:** Tool list is narrower than rev 4 (~18 tools vs 20). Six tools need bespoke JSON parsers (trufflehog, detect-secrets, depcheck, deptry, kube-score, govulncheck) — documented as "legacy JSON adapter" with planned SARIF migration when upstream supports it.

### Tool battery

**Required (baseline; no degradation):**
| Tool | Output | Role |
|------|--------|------|
| `semgrep` | SARIF | Multi-language SAST + all custom rulesets |
| `gitleaks` | SARIF | Secrets + git history |

**Optional SARIF adapters (thin — native SARIF):**
`trivy` (config + fs), `checkov`, `hadolint`, `actionlint`, `kube-linter`, `bandit`, `gosec`, `bearer`, `osv-scanner`, `grype`, `trufflehog`

**Optional bespoke-JSON adapters (SARIF not yet available upstream — each ≤ 40 LOC):**
`detect-secrets`, `depcheck`, `deptry`, `kube-score`, `govulncheck` (SARIF roadmap not confirmed upstream — treat as permanent bespoke adapter unless this changes)

Note: `trufflehog` v3 emits SARIF via `--output sarif` — moved to SARIF tier above.

**User-visible labeling:** The tier labels ("SARIF adapter", "bespoke-JSON adapter") are internal maintenance vocabulary. Install output groups tools by **capability tier** only (secrets / IaC / CI-CD / supply-chain / SAST / data-flow). Tier-implementation labels never surface in user-facing output.

**Custom scripts shipped by agentic-dev-team (emit SARIF natively):**
`entropy-check.py` — passphrase entropy + cross-env reuse
`model-hash-verify.py` — ML model integrity + provenance

**Custom scripts shipped by agentic-security-review (emit appropriate format):**
`shared-cred-hash-match.py` — cross-repo shared credentials (SARIF)
`service-comm-parser.py` — NATS/K8s/package configs → Mermaid (not a SARIF finding)

**Semgrep rulesets shipped:**
Community: `p/security-audit`, `p/owasp-top-ten`, `p/nodejs`, `p/python`, `p/java`, `p/go`, `p/secrets`, `p/insecure-transport`, `p/cryptography`, `p/xss`, `p/sql-injection`, `p/command-injection`, `p/dockerfile`, `p/kubernetes`.
Custom (shipped in `knowledge/semgrep-rules/`): `ml-patterns.yaml` (ONNX/Kryo/pickle/deserialization), `llm-safety.yaml` (prompt-template injection, hardcoded LLM keys, insecure model loading), `fraud-domain.yaml` (fail-open and score-manipulation patterns).

Note on LLM-safety and prompt-injection scanners (`garak`, `rebuff`, `PyRIT`): these are runtime testing tools, not static scanners. Integration is deferred to Phase C (red-team) if needed; **static coverage via `llm-safety.yaml` is intentionally narrow — it catches pattern-visible issues (hardcoded LLM keys, insecure model loading, prompt-template string injection) but is NOT a substitute for runtime LLM safety testing.** CLAUDE.md and the README must carry this bound explicitly.

### Adapter Maintenance Policy

- **Owners:** `static-analysis-integration` skill frontmatter declares `maintainers:` as a list of at least 2 names (bus-factor minimum)
- **Escalation:** auto-issue from tier-2 CI failure unassigned for > 14 days escalates to plugin CODEOWNERS
- **Update trigger:** tier-2 CI job runs each adapter against the installed binary; any SARIF/JSON schema drift fails CI and opens an auto-issue
- **Deprecation:** adapter failing CI for three consecutive releases AND upstream unmaintained for > 6 months → demoted to "deprecated" (still shipped, emits warning on invocation); removed in next major contract version
- **Adding a tool:** requires a fixture pair (mock output + expected unified finding) and a SARIF adapter first; bespoke-JSON adapters only if SARIF is genuinely unavailable upstream

### Ruleset Maintenance Policy (custom semgrep rulesets)

Separate from adapter maintenance — rulesets track evolving attack patterns, not tool schema drift.

- **Owners:** each ruleset (`ml-patterns.yaml`, `llm-safety.yaml`, `fraud-domain.yaml`) has `maintainers:` (min 2) in a frontmatter block at the top of the YAML file
- **Review cadence:** quarterly — reviewers confirm patterns are still relevant, add new attack signatures, retire deprecated ones
- **False-positive drift threshold:** if eval fixtures show > 20% positive-match noise on the tier-2 suite, ruleset is paused and triaged within one release
- **Community-PR intake:** PRs adding patterns require a positive fixture + negative fixture; rejections must cite the policy
- **Deprecation:** a ruleset with no review or change in two consecutive review cycles is demoted to "archived" unless a maintainer re-ups

## Primitives Contract Versioning

`plugins/agentic-dev-team/knowledge/security-primitives-contract.md` with semver frontmatter. Contents: agent IDs, skill IDs, three JSON schemas:
1. **RECON envelope** — normalized reconnaissance output
2. **Unified finding envelope** — narrow normalization of SARIF `result` (file, line, rule_id, severity, message, metadata). Per-tool raw outputs are NOT in the contract.
3. **Disposition register** — FP-reduction output

Semver: PATCH = doc; MINOR = additive; MAJOR = breaking. Consumer declares `required-primitives-contract: ^1.0.0`.

## Acceptance Criteria

### Primitives (agentic-dev-team)
- [ ] `codebase-recon` produces a contract-conformant RECON artifact including git-history overview
- [ ] `ACCEPTED-RISKS.md` convention: suppresses matched findings with logging; `--init-risks` scaffolds when absent
- [ ] `static-analysis-integration` uses SARIF-first parsing; adapters (SARIF + JSON) detect tool presence, emit `install with: ...` hint per missing tool, never fail the pipeline
- [ ] Install-hint format is consistent: `<tool-name> — <capability-tier>. install: <package-manager> install <name>` (one format across all tools); required tools visually distinguished from optional (e.g., `[REQUIRED]` prefix); tier-implementation labels ("SARIF adapter" / "bespoke-JSON adapter") never surface in user-facing output
- [ ] CLAUDE.md and README in `agentic-security-review` each contain the `llm-safety.yaml` coverage-bound statement verbatim (not paraphrased): "static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing"
- [ ] Custom scripts (`entropy-check.py`, `model-hash-verify.py`) emit SARIF and pass schema validation
- [ ] Semgrep rulesets are shipped: community list + three custom rulesets (`ml-patterns.yaml`, `llm-safety.yaml`, `fraud-domain.yaml`); each custom ruleset has a positive+negative fixture
- [ ] Primitives contract v1.0.0 exists; unified finding schema is a narrow SARIF-derived envelope (no per-tool raw output); conformance fixture passes under `evals/primitives-contract/`
- [ ] `PreToolUse: contract-version-guard.sh` blocks writes to `security-primitives-contract.md` without a same-commit version bump. Bypass only for release-please commits (detected via commit-author match `release-please[bot]` or message-prefix `chore(main): release`)
- [ ] Adapter Maintenance Policy documented in `static-analysis-integration/SKILL.md` with maintainer, update trigger, deprecation path
- [ ] Tier-2 CI job runs each adapter against its installed binary (separate from unit tests that use mocked output)

### Conventions-in-flight (from combined-plan-opus-4-7-security-review.md, rev 7)

These three ACs ensure P2 execution stays aligned with P1 (`plans/opus-4-7-alignment.md`) conventions so that P1's Stage 7 is verification rather than a multi-file retrofit. Each AC adds ~15 minutes per affected commit.

- [ ] **AC-CIF-1 (Opus-tier agents carry thinking directive)**: Any new file added under `plugins/agentic-dev-team/agents/` or `plugins/agentic-security-review/agents/` whose YAML frontmatter declares `model: opus` must contain the literal sentence `Think carefully and step-by-step; this problem is harder than it looks.` as an H2 subsection titled `## Thinking Guidance` placed immediately after the frontmatter close (`---`) and before any other heading. The body of the subsection is exactly that one sentence. Any new file with `model: haiku` must contain the literal sentence `Prioritize responding quickly rather than thinking deeply.` in the same placement. Impacted new opus agents (per this plan): `codebase-recon`, `fp-reduction`, `business-logic-domain-review`, `cross-repo-synthesizer`, `exec-report-generator`, `redteam-recon-analyzer`, `redteam-evasion-analyzer`, `redteam-extraction-analyzer`, `redteam-report-generator` (9 files). Source: Anthropic's official "Best Practices for Claude Opus 4.7 with Claude Code" post (`https://claude.com/blog/best-practices-for-using-claude-opus-4-7-with-claude-code`). Verification: P1 Step 7 ships `scripts/check-thinking-directives.sh` as the Stage 7 gate; during P2 execution reviewers verify manually at commit time.
- [ ] **AC-CIF-2 (CLAUDE.md additions follow architecture rule)**: New content added to `plugins/agentic-dev-team/CLAUDE.md` during P2 execution must be *needed every session*. Reference data (schemas, registries, policy tables) goes in `plugins/agentic-dev-team/knowledge/`; procedures go in `plugins/agentic-dev-team/skills/`; CLAUDE.md receives at most a one-line pointer per relocated block. Exception: registry summary rows for new agents/skills/commands may appear in CLAUDE.md's existing `### Quick Reference` section. Verification: review at P2 commit time; P1 Step 3 ships `scripts/check-links.sh` as the Stage 7 gate.
- [ ] **AC-CIF-3 (New negative rules pre-classified)**: Any new line added to `{plugins/agentic-dev-team/agents/orchestrator.md, plugins/agentic-dev-team/commands/build.md, plugins/agentic-dev-team/commands/plan.md, plugins/agentic-dev-team/commands/code-review.md, plugins/agentic-dev-team/CLAUDE.md}` during P2 execution matching `^.*(Do not|DO NOT|Don't|DON'T|Never|NEVER)` must be preceded by `<!-- SAFETY-GATE: <1-line reason> -->` (destructive / security / data-loss protection — keep negative) OR converted to a positive exemplar block containing the literal strings `Example 1:` and `Example 2:` (process rules). Rules that would classify as `NATIVE` (Opus 4.7 handles without the rule) should not be added. Verification: P1 Step 5 ships `scripts/check-negative-rules.sh` as the Stage 7 gate.

### Companion plugin (agentic-security-review)
- [ ] Plugin directory follows Structure Contract; `install.sh` refuses on major primitives-contract mismatch, reports tool-presence grouped by capability tier, and prints the exact `settings.local.json` opt-out snippet inline
- [ ] **Hooks default ON** in this plugin only; hooks are NOT registered in agentic-dev-team
- [ ] `PostToolUse: static-scan-on-edit.sh` fires on relevant file writes, default severity threshold **error only** (warnings require `verbose_hooks: true` in settings); fast-tier tools only (gitleaks, hadolint, actionlint, semgrep-quick-profile); `settings.local.json` opt-out verified by an eval that disables the hook and asserts it does not fire
- [ ] `fp-reduction` hybrid: joern call-graph when present; LLM-only fallback when absent with disposition entries tagged `reachability_source: llm-fallback`
- [ ] Exec report Section 0 carries a **fallback-mode banner** when any finding has `reachability_source: llm-fallback` — banner text quantifies loss: "Reachability stage used LLM reasoning instead of call-graph analysis; dead-code paths may be less accurate. Stages 2–5 unaffected."
- [ ] `business-logic-domain-review` covers fail-open, score manipulation, emulation mode, model-endpoint confusion, tokenization bypass, feature poisoning, replay/idempotency
- [ ] `tool-finding-narrative-annotator` produces consolidated narratives in four domains (PII flow, ML edge cases, NATS/messaging auth, crypto cross-file)
- [ ] `compliance-mapping` runs pattern-table first (`knowledge/compliance-patterns.yaml` — schema includes `pattern_regex, field_type, regulation, control_id, citation, llm_review_trigger`); LLM invoked only when `llm_review_trigger` is truthy for a finding; report header has compliance disclaimer; test asserts exact LLM call count via injected call-counter
- [ ] `service-comm-parser.py` emits Mermaid from NATS/K8s/package configs; `/cross-repo-analysis` composes `shared-cred-hash-match.py` + `service-comm-parser.py` + `cross-repo-synthesizer` agent
- [ ] `/security-assessment <path>` runs recon → tool battery → LLM narrative agents → FP-reduction → compliance → service-comm diagram → exec report; `--start`, `--agents`, `--fp-reduce` flags work
- [ ] Executive report Section 0 "Top 3 Actions" each has owner/effort/blocking-id; Section 4 embeds Mermaid diagram verbatim (exec-report-generator passes through, does not re-render)
- [ ] **Red-team target scope**: `/redteam-model` accepts only localhost + `127.0.0.0/8` + `10.0.0.0/8` + `172.16.0.0/12` + `192.168.0.0/16` + `::1` by default; public targets require `--self-certify-owned` + artifact whose SHA-256 is logged
- [ ] Consent-gate refusal message includes a one-line example of `authorization.md` format AND confirms `redteam-authorization.md` is shipped (not just referenced)
- [ ] `/redteam-model` supports `--dry-run` (still enforces scope), `--start`, `--agents`; flag-interaction matrix documented; `--start <phase-token>` accepts exactly the token printed by the progress manifest (acceptance test copies the printed token verbatim)
- [ ] Rate-limit + budget enforced via injectable mock clock with explicit interface: `class MockClock { now() -> float; advance(seconds: float) -> None }`; test records inter-request deltas on the mock
- [ ] Each red-team probe emits a schema-conformant artifact; failures produce `<phase>.error.json`
- [ ] Mid-run failure writes `results/progress-manifest.json` + prints "Resume with --start <phase>" (message owned by `harness/redteam/lib/result_store.py`)
- [ ] Red-team report cites every finding by artifact ID
- [ ] `/export-pdf` prints absolute output path on success; skips gracefully when `pandoc` and `weasyprint` both absent
- [ ] Two-plugin install UX: `install.sh` names missing deps with exact install commands, grouped by capability tier
- [ ] `knowledge/agent-registry.md` and both CLAUDE.md files updated; `/agent-audit` passes both plugins
- [ ] Release-please per-plugin component config: `feat(security-review):` bumps only the companion

## User-Facing Behavior

```gherkin
Feature: Primitives in agentic-dev-team

  Scenario: Recon produces contract-conformant artifact with git history
    Given a multi-file repository
    When codebase-recon runs
    Then a RECON file is written to memory/ including git-history overview
    And the artifact validates against the RECON schema in security-primitives-contract.md

  Scenario: Accepted risks are suppressed with logging
    Given ACCEPTED-RISKS.md declares one rule that matches one file
    And a second rule that matches nothing
    When /code-review runs
    Then no finding is emitted for the matched accepted rule
    And the report contains exactly one suppression note

  Scenario: SARIF-first static analysis runs available tools
    Given semgrep, trivy, and hadolint are on PATH; checkov is absent
    When the static-analysis pre-pass runs
    Then semgrep, trivy, and hadolint run and emit SARIF
    And their SARIF results normalize to the unified finding envelope
    And checkov is reported: "checkov — IaC policy scanning. install: pip install checkov"
    And the pipeline exits successfully

  Scenario: Custom ruleset catches ML-pattern
    Given a Python file loads an ONNX model without integrity verification
    When semgrep runs with knowledge/semgrep-rules/ml-patterns.yaml
    Then a finding is produced with rule_id naming the ML-pattern check

  Scenario: PreToolUse contract-version-guard allows release-please commits
    Given a release-please[bot] commit modifies security-primitives-contract.md version
    When the Edit is attempted
    Then the hook allows the write
    And an audit-log entry records the bypass

  Scenario: PreToolUse contract-version-guard blocks unversioned human edits
    Given a human-authored Edit to security-primitives-contract.md without a version bump in the diff vs HEAD
    When the Edit is attempted
    Then the hook blocks with a message naming the required bump type

Feature: Security plugin — hooks, tool-first scanning, FP-reduction

  Scenario: Hooks default ON in security plugin only
    Given a fresh install of agentic-security-review
    When a Dockerfile is written via Edit
    Then the PostToolUse hook runs hadolint
    And findings at severity "error" are surfaced

  Scenario: Hook default threshold suppresses warnings
    Given PostToolUse hook runs semgrep and hadolint
    And semgrep emits one error-level and one warning-level finding on the edit
    Then only the error-level finding is surfaced
    And the warning-level finding is recorded but not displayed

  Scenario: Hook opt-out via settings.local.json
    Given settings.local.json sets hook "static-scan-on-edit" to disabled
    When a Dockerfile is written
    Then the hook does NOT fire

  Scenario: Hook fires on secret-pattern write
    Given a file is written containing the pattern AWS_ACCESS_KEY_ID=AKIA...
    When the PostToolUse hook runs gitleaks
    Then a finding is surfaced immediately
    And the finding severity is "error"

  Scenario: Install output prints opt-out snippet inline
    Given a fresh install of agentic-security-review
    Then the install report prints a capability-tier grouped tool-presence summary
    And the install report includes the exact JSON to paste into settings.local.json for hook opt-out

  Scenario: FP-reduction uses joern when present
    Given a fixture codebase and aggregated findings
    And joern is on PATH
    When fp-reduction runs
    Then joern builds the call graph deterministically
    And reachability for each finding matches the fixture CPG

  Scenario: FP-reduction fallback-mode banner in exec report
    Given joern is absent
    When /security-assessment completes
    Then each finding's disposition has reachability_source: llm-fallback
    And the exec report Section 0 contains: "Reachability stage used LLM reasoning instead of call-graph analysis; dead-code paths may be less accurate. Stages 2-5 unaffected."

  Scenario: Compliance mapping invokes LLM only when table flags ambiguous
    Given four findings: three match pattern-table entries deterministically
    And one matches a pattern with llm_review_trigger=true
    When compliance-mapping runs with an injected LLM call-counter
    Then the counter records exactly one LLM invocation

  Scenario: Service-comm diagram embedded verbatim
    Given service-comm-parser emits a Mermaid block
    When exec-report-generator produces Section 4
    Then the Mermaid block appears verbatim with no re-rendering

  Scenario: Cross-repo shared credentials detected
    Given two repos both contain the hash of password "Welcome2ACI"
    When /cross-repo-analysis runs
    Then shared-cred-hash-match reports one shared credential across two repos
    And cross-repo-synthesizer produces a named attack chain citing findings by ID

Feature: Security plugin — adversarial ML red-team

  Scenario: Public target refused without self-cert
    Given target URL https://api.example.com/predict
    When /redteam-model is invoked without --self-certify-owned
    Then the command prints the refusal message including a one-line authorization.md example
    And exits non-zero

  Scenario: Self-cert with missing artifact fails with named file
    Given --self-certify-owned /tmp/missing.md
    Then the command names /tmp/missing.md and exits non-zero

  Scenario: Rate-limit and budget are deterministic
    Given a MockClock is injected into the HTTP client
    And rate-limit 5/sec and budget 10000
    When the pipeline runs against a mock target
    Then the mock clock records inter-request deltas all >= 200ms
    And on reaching 10000 queries the pipeline stops with status "budget_exhausted"

  Scenario: Mid-run failure writes progress manifest
    Given the pipeline fails at phase 05
    Then results/progress-manifest.json lists phases 01-04 with artifact paths
    And the command prints "Resume with --start 05"

  Scenario: --start accepts the exact printed token
    Given the progress manifest printed "Resume with --start 05"
    When /redteam-model is invoked with --start 05
    Then the command resumes at phase 05 successfully

  Scenario: --dry-run with --start skips artifact check
    When /redteam-model runs with --dry-run --start 04
    Then no HTTP calls are made
    And no missing-artifact check fires
    And the planned step graph from phase 04 is printed
```

## Steps

### Phase A — Primitives in agentic-dev-team

#### Step 1: codebase-recon agent — **MVP Core**

**Complexity**: standard
**RED**: `evals/codebase-recon/` — two fixtures (TS monorepo + polyglot) + rubric file defining what "correct entry-point identification" means. Assert RECON includes git-history section (branches, cert/key file history, recent activity). Placeholder schema in this step; Step 4 finalizes via symbol import.
**GREEN**: `plugins/agentic-dev-team/agents/codebase-recon.md` implementing the seven-step procedure. Writes `memory/recon-<slug>.{md,json}`.
**REFACTOR**: Extract file-classification patterns to `knowledge/recon-patterns.md` if duplication emerges
**Files**: `plugins/agentic-dev-team/agents/codebase-recon.md`, `evals/codebase-recon/{fixtures/,rubric.md,expected-schema.json}`, `knowledge/agent-registry.md`, `plugins/agentic-dev-team/CLAUDE.md`
**Commit**: `feat: add codebase-recon agent with git history overview`

#### Step 2: ACCEPTED-RISKS.md convention + scaffold

**Complexity**: standard
**RED**: Fixture with two rules (one matched, one unmatched). Assert exactly one suppression note; unrelated findings unaffected. `--init-risks` test: missing file → template written + exit 0.
**GREEN**: Schema in `knowledge/accepted-risks-schema.md`; template at `templates/ACCEPTED-RISKS.md.tmpl`. Update `/code-review`, `review-agent`, and `security-review` to consult the file.
**REFACTOR**: Move suppression to a post-pass filter if per-agent context cost is high
**Files**: `plugins/agentic-dev-team/commands/code-review.md`, `commands/review-agent.md`, `knowledge/accepted-risks-schema.md`, `templates/ACCEPTED-RISKS.md.tmpl`, `agents/security-review.md`, `evals/accepted-risks/`
**Commit**: `feat: support ACCEPTED-RISKS.md project-local policy carveouts`

#### Step 3a: SARIF-first baseline (required tools + shared parser) — **MVP Core**

**Complexity**: complex
**RED**: Tier-1 unit tests with mocked SARIF input for `semgrep` + `gitleaks` + `trivy` + `hadolint` + `actionlint` (the 80% coverage subset). Tier-2 nightly CI job runs each adapter against the installed binary in a Docker image. Install-hint format consistency test across the 5 tools. Shared SARIF parser normalizes `result` objects to the unified finding envelope.
**GREEN**: `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md` defines the SARIF parser (shared across tools), per-tool detection + invocation, install-hint per tool, adapter + ruleset maintenance policies in frontmatter (`maintainers:` as list, min 2).
**REFACTOR**: None at this scale
**Files**: `skills/static-analysis-integration/SKILL.md`, `skills/static-analysis-integration/references/tool-configs.md`, `evals/static-analysis-tools/{tier1-mocks/,tier2-integration/}`
**Commit**: `feat: SARIF-first tool orchestration baseline (required 5 adapters)`

#### Step 3b: SARIF optional + bespoke-JSON + custom scripts + rulesets

**Complexity**: complex
**RED**: Tier-1 + tier-2 for the optional SARIF adapters (checkov, kube-linter, bandit, gosec, bearer, osv-scanner, grype, trufflehog) and bespoke-JSON adapters (detect-secrets, depcheck, deptry, kube-score, govulncheck — each ≤40 LOC). Custom scripts (`entropy-check.py`, `model-hash-verify.py`) emit SARIF that passes schema validation. Three custom semgrep rulesets each have positive + negative fixtures under `evals/semgrep-rulesets/{ml-patterns,llm-safety,fraud-domain}/`. Adapter-deprecation path (3 consecutive failing releases → warn-only) exercised via mock.
**GREEN**: Extend the Step 3a skill with optional adapters, custom scripts under `tools/{entropy-check.py,model-hash-verify.py}`, rulesets under `semgrep-rules/{ml-patterns.yaml,llm-safety.yaml,fraud-domain.yaml}` each with a `maintainers:` YAML-frontmatter block.
**REFACTOR**: Split `references/tool-configs.md` per-tool if it exceeds 1500 lines
**Files**: same skill dir extended, `tools/{entropy-check.py,model-hash-verify.py}`, `semgrep-rules/{ml-patterns.yaml,llm-safety.yaml,fraud-domain.yaml}`, `evals/semgrep-rulesets/`
**Commit**: `feat: SARIF-first tool orchestration optional tier + custom scripts + rulesets`

#### Step 4: Primitives contract + conformance fixture

**Complexity**: complex
**RED**: `evals/primitives-contract/` exercises each primitive against its schema. Mutation test: alter a schema field → CI fails. Version-mismatch mock: producer 2.0.0 vs. consumer `^1.0.0` → install.sh refuses.
**GREEN**: `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` with `version: 1.0.0` frontmatter. Contents: agent IDs, skill IDs, three JSON schemas (RECON envelope, unified finding envelope narrow-SARIF-derived, disposition register). Per-tool raw outputs explicitly NOT in contract. `/agent-audit` extended to validate references.
**REFACTOR**: Split inline JSON into `knowledge/schemas/*.json` if file exceeds 400 lines
**Files**: `knowledge/security-primitives-contract.md`, `knowledge/schemas/` (optional), `commands/agent-audit.md`, `evals/primitives-contract/`
**Commit**: `feat: publish versioned security-primitives-contract v1.0.0`

#### Step 5: PreToolUse contract-version-guard hook

**Complexity**: trivial
**RED**: (a) human Edit to `security-primitives-contract.md` without version bump in proposed-content-vs-HEAD diff → blocked with required-bump-type message; (b) Edit with version bump → allowed; (c) release-please[bot] commit or `chore(main): release` message → bypass with audit entry.
**GREEN**: `hooks/contract-version-guard.sh` inspects the diff between proposed new content and HEAD (not git staging), parses frontmatter versions, requires a bump when body changes. Bypass checks commit author/message via env vars exposed by the hook framework.
**REFACTOR**: None
**Files**: `hooks/contract-version-guard.sh`, `hooks/guards.json`, `settings.json`
**Commit**: `feat: guard primitives-contract edits with semver-bump requirement`

### Phase B — Companion plugin: static assessment

#### Step 6: Plugin scaffold + harness/ + install UX

**Complexity**: standard
**RED**: Structure-parity assertion. `/agent-audit` passes. `install.sh` tests: (a) agentic-dev-team missing → non-zero + install hint; (b) primitives-contract major mismatch → non-zero + version names; (c) missing optional tools → warning list grouped by capability tier, not failure; (d) install output prints the exact `settings.local.json` opt-out snippet inline.
**GREEN**: Scaffold mirrored layout including `harness/` placeholder. `plugin.json` declares `required-primitives-contract: ^1.0.0`. `install.sh` does dep + contract + tool-presence checks, groups output by capability tier (secrets / IaC / CI-CD / supply-chain / SAST / data-flow), **distinguishes required from optional tools visually (required shown with `[REQUIRED]` prefix; absence is a hard failure vs. optional absence which is a warning)**, and prints the exact opt-out JSON snippet. CLAUDE.md documents hook opt-out and adapter + ruleset policies.
**REFACTOR**: Share install.sh helpers with agentic-dev-team via sourced snippet
**Files**: full `plugins/agentic-security-review/` tree + `.claude-plugin/marketplace.json`
**Commit**: `feat(security-review): scaffold companion plugin`

#### Step 7: PostToolUse static-scan-on-edit hook (security plugin only)

**Complexity**: standard
**RED**: (a) Dockerfile write → hadolint fires if present; skip if absent; default severity threshold = error; warnings suppressed unless `verbose_hooks: true`. (b) `.github/workflows/*.yml` write → actionlint fires. (c) JS/TS write → semgrep quick-profile fires. (d) File with AWS key pattern → gitleaks fires with error severity. (e) **Negative case:** write of an unmatched file type (e.g., `.txt`, `.md` without secret patterns) → no tool fires, no finding surfaced. (f) `settings.local.json` hook opt-out → hook does NOT fire (verified by opt-out eval).
**GREEN**: `plugins/agentic-security-review/hooks/static-scan-on-edit.sh` — file-extension matcher dispatches to fast-tier tools (gitleaks, hadolint, actionlint, semgrep with quick profile only). Registered in `plugins/agentic-security-review/settings.json` — not agentic-dev-team. Default severity = error; `settings.local.json` can set `"verbose_hooks": true` to surface warnings. Opt-out JSON snippet documented in install output.
**REFACTOR**: Extract tool-matcher regex to `hooks/static-scan-matchers.conf` for maintainability
**Files**: `plugins/agentic-security-review/hooks/static-scan-on-edit.sh`, `hooks/static-scan-matchers.conf`, `settings.json`, `evals/hook-opt-out/`
**Commit**: `feat(security-review): PostToolUse auto-scan hook, error-severity default, security-plugin only`

#### Step 8: FP-reduction hybrid (joern + LLM with fallback banner) — **MVP Core**

**Complexity**: complex
**RED**: Fixture aggregated findings + **fixture CPG** (joern-export CSV/JSON checked into `evals/fp-reduction/cpg-fixtures/`). Two modes: (a) joern present → reachability verdicts match CPG deterministically; (b) joern absent → verdicts produced by LLM, each tagged `reachability_source: llm-fallback`. Stages 2–5 produce correct dispositions with documented reasons in both modes. Rubric file defines what "correct disposition reason" means for eval grading.
**GREEN**: `skills/false-positive-reduction/SKILL.md` describes 5-stage rubric + dispatch. `agents/fp-reduction.md` (opus) consumes findings + CPG (if present). Joern invocation wrapped in `skills/false-positive-reduction/tools/reachability.sh` (runs `joern-parse` + `joern-export --repr cfg` + filter to entry points). Output includes `reachability_source` per finding for downstream fallback-banner logic.
**REFACTOR**: Cache call-graph per commit hash under `memory/joern-cache/<sha>.cpg` if build time exceeds 30s
**Files**: `skills/false-positive-reduction/SKILL.md`, `skills/false-positive-reduction/tools/reachability.sh`, `agents/fp-reduction.md`, `evals/fp-reduction/{fixtures/,cpg-fixtures/,rubric.md}`
**Commit**: `feat(security-review): hybrid FP-reduction (joern + LLM stages 2-5) with fallback banner`

#### Step 9: business-logic-domain-review agent — **MVP Core**

**Complexity**: complex
**RED**: Fixture codebase with seven seeded fraud-domain bugs (fail-open, score-zero sub, emulation mode in prod, model-endpoint confusion, tokenization-skip under flag, feature poisoning, missing replay idempotency). Rubric file defines grading: one finding per seeded bug with attack-scenario narrative.
**GREEN**: `agents/business-logic-domain-review.md` (opus) reads `knowledge/domain-logic-patterns.md`.
**REFACTOR**: Split `domain-logic-patterns.md` by industry if patterns diverge
**Files**: `agents/business-logic-domain-review.md`, `knowledge/domain-logic-patterns.md`, `evals/business-logic-domain/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): business-logic domain-review agent`

#### Step 10: tool-finding-narrative-annotator agent

**Complexity**: standard
**RED**: Four fixtures (PII flow bridge, ONNX + eval() in metadata, NATS no_auth + management endpoint, cross-env passphrase reuse + weak bcrypt) + rubric file. Assert one consolidated narrative per domain citing tool rule-IDs.
**GREEN**: `agents/tool-finding-narrative-annotator.md` (sonnet). Consumes SARIF-normalized findings + RECON.
**REFACTOR**: Split into domain specialists if narrative styles diverge sharply
**Files**: `agents/tool-finding-narrative-annotator.md`, `knowledge/narrative-annotation-patterns.md`, `evals/narrative-annotator/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): tool-finding narrative annotator (PII/ML/auth/crypto)`

#### Step 11: Compliance-mapping (pattern-table first + LLM call-counter)

**Complexity**: standard
**RED**: Fixtures: (a) PAN at DEBUG → PCI-DSS 3.4 + 10.2 deterministic; (b) unencrypted Mongo → PCI-DSS 3.4 + GDPR Art 32 deterministic; (c) no CSRF on admin → no mapping; (d) finding matching `llm_review_trigger=true` entry → LLM invoked exactly once. **LLM call-counter interface:** `class LLMCallCounter { invoke(prompt, context) -> response; count() -> int; reset() -> None }` — injected into the skill's LLM invocation layer; test asserts `counter.count() == 1`. Rubric file defines what "correct annotation" means for the ambiguous case.
**GREEN**: `skills/compliance-mapping/SKILL.md` runs pattern-table first. `knowledge/compliance-patterns.yaml` schema: `{pattern_regex, field_type, regulation, control_id, citation, llm_review_trigger: bool}`. LLM edge-annotator invoked only when `llm_review_trigger=true`. Report header carries "informational, not audit-grade" disclaimer.
**REFACTOR**: Split YAML per regulation if > 500 entries
**Files**: `skills/compliance-mapping/SKILL.md`, `knowledge/compliance-patterns.yaml`, `agents/compliance-edge-annotator.md`, `evals/compliance-mapping/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): pattern-first compliance mapping with LLM call-count eval`

#### Step 12: Service-comm-diagram tool + /cross-repo-analysis (before exec report)

**Complexity**: standard
**RED**: (a) Fixture repo with NATS + K8s Services + package.json inter-service calls → `service-comm-parser.py` emits Mermaid; edges annotated with auth/encryption status. (b) Fixture two repos both containing hash of `"Welcome2ACI"` → `shared-cred-hash-match.py` reports shared cred. (c) `/cross-repo-analysis <paths>` composes both tools then invokes `cross-repo-synthesizer` which produces a named attack chain.
**GREEN**: `plugins/agentic-security-review/harness/tools/service-comm-parser.py` and `harness/tools/shared-cred-hash-match.py` (shipped in companion plugin; they have no agentic-dev-team caller). `commands/cross-repo-analysis.md` orchestrates. `agents/cross-repo-synthesizer.md` (opus) produces narrative. Parser output is a Mermaid code block; passed through verbatim by downstream consumers.
**REFACTOR**: None
**Files**: `commands/cross-repo-analysis.md`, `agents/cross-repo-synthesizer.md`, `harness/tools/{service-comm-parser.py,shared-cred-hash-match.py}`, `evals/cross-repo/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): service-comm diagram + /cross-repo-analysis`

#### Step 13: /security-assessment command + orchestration skill — **MVP Core**

**Complexity**: complex
**RED**: E2E against fixture repo with seeded vulnerabilities. Split 13a (pipeline shape — RECON + tool outputs + LLM-agent outputs + FP-reduction + compliance + service-comm diagram all present) / 13b (defer exec-report content assertions to Step 14). `--start`, `--agents`, `--fp-reduce` flags behave correctly.
**GREEN**: `commands/security-assessment.md` + `skills/security-assessment-pipeline/SKILL.md`. Declarative step graph with `depends_on`. Consumes agentic-dev-team primitives via contract; consumes companion's fp-reduction, business-logic-domain-review, tool-finding-narrative-annotator, compliance-mapping, service-comm parser.
**REFACTOR**: Adopt `memory/` progress-file pattern if phase handoff bloats context
**Files**: `commands/security-assessment.md`, `skills/security-assessment-pipeline/SKILL.md`, `evals/security-assessment/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): /security-assessment orchestrated pipeline`

#### Step 14: Executive report generator (with fallback banner)

**Complexity**: standard
**RED**: Fixture disposition register + compliance annotations + Mermaid diagram + business-logic findings → assert Sections 0–6 present. Section 0 Top 3 Actions each has owner/effort/blocking-id. **Section 4 embeds the Mermaid block via exact string equality (not hash comparison) after normalizing line endings (CRLF → LF) on both sides**; the service-comm-parser raw output is the left operand and the Section 4 excerpt is the right. Header has compliance disclaimer. If any finding has `reachability_source: llm-fallback`, Section 0 contains the fallback-mode banner verbatim.
**GREEN**: `agents/exec-report-generator.md` (opus). Pure narrative synthesis over structured inputs. Mermaid block passed through unchanged (prompt instruction).
**REFACTOR**: Factor section templates into `knowledge/report-sections.md`
**Files**: `agents/exec-report-generator.md`, `knowledge/report-sections.md`, `evals/exec-report/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): executive report generator with joern-fallback banner`

### Phase C — Adversarial ML red-team (self-owned targets)

#### Step 15: Red-team harness scaffold + scope + consent

**Complexity**: complex
**RED**: Harness unit tests against mock target:
- Config validation
- Rate-limit with injectable `MockClock { now() -> float; advance(seconds: float) -> None }`; assertions record inter-request deltas
- Budget enforcement
- Dry-run: zero HTTP calls
- Step-graph dependency handling
- Scope enforcement (public without `--self-certify-owned` → refuse; private CIDR → accept; missing self-cert artifact named in error)
- Audit-log SHA-256 of self-cert artifact
- `--dry-run` still enforces scope
- PreToolUse hook blocks `python orchestrator`, `python -m redteam.orchestrator`, absolute/relative paths without `REDTEAM_AUTHORIZED=1`
- `--start <token>` accepts verbatim the token printed by result_store in a prior failed run

**GREEN**: `harness/redteam/{orchestrator.py, config.py, requirements.txt, lib/*}` — `http_client.py` rate-limited with injectable clock; `scope_check.py` CIDR + host allowlist + artifact hashing; `result_store.py` owns progress-manifest + `"Resume with --start <phase>"` message; `scoring.py` per-probe scoring helpers. `skills/adversarial-ml-redteam/SKILL.md` methodology + safety. `commands/redteam-model.md` wraps harness: scope + self-cert checks, then exports `REDTEAM_AUTHORIZED=1` into child env only. `hooks/redteam-guard.sh` matcher covers all invocation forms. `knowledge/redteam-authorization.md` shipped with one-line example inline in refusal message and full format reference in the file. Flag-interaction note covers `--dry-run`+`--start`, `--agents` precedence. `install.sh` checks Python 3.10+ + requirements.
**REFACTOR**: Split orchestrator + step registry if harness > 500 LOC
**Files**: `harness/redteam/{orchestrator.py,config.py,requirements.txt,lib/*}`, `skills/adversarial-ml-redteam/SKILL.md`, `commands/redteam-model.md`, `hooks/redteam-guard.sh`, `settings.json`, `knowledge/redteam-authorization.md`, `install.sh`, `evals/redteam-scaffold/`
**Commit**: `feat(security-review): red-team harness with self-owned scope + consent gate`

#### Step 16: Red-team probes — recon, schema, sensitivity, boundary

**Complexity**: complex
**RED**: FastAPI mock-target fixture with deterministic responses. Each probe emits schema-conformant artifact; failure emits `<phase>.error.json`. Happy + network-error paths per probe.
**GREEN**: `harness/redteam/probes/{01_api_recon.py, 02_schema_discovery.py, 03_feature_sensitivity.py, 04_boundary_mapping.py}`. Schemas under `harness/redteam/schemas/`.
**REFACTOR**: Extract mutation patterns into `lib/feature_dict.py`
**Files**: `harness/redteam/probes/{01..04}_*.py`, `harness/redteam/schemas/`, `harness/redteam/lib/feature_dict.py`, `evals/redteam-probes/`
**Commit**: `feat(security-review): red-team recon + boundary probes`

#### Step 17: Red-team attacks — evasion, input-validation, extraction

**Complexity**: complex
**RED**: Mock-target tests. Each attack emits schema-conformant findings with evidence pairs. Rate-limit + budget honored.
**GREEN**: `harness/redteam/probes/{05_evasion_attack.py, 06_input_validation.py, 07_model_extraction.py}`.
**REFACTOR**: Add `--budget-per-phase` if extraction dominates total budget
**Files**: `harness/redteam/probes/{05..07}_*.py`, `evals/redteam-attacks/`
**Commit**: `feat(security-review): red-team evasion/fail-open/extraction`

#### Step 18: Red-team analysis agents + report

**Complexity**: standard
**RED**: Fixture probe artifacts → `redteam-report-generator` produces a document with exec summary, per-phase findings citing artifact IDs, mitigations, risk register. Mid-run-failure fixture: progress manifest present, partial report generated listing completed phases. Handoff contract: given `results/progress-manifest.json` listing 7 completed phases, command dispatches exactly 7 analyzer invocations with correct artifact paths. Rubric file grades narrative quality.
**GREEN**: Python orchestrator writes artifacts only; Claude command post-run step reads progress-manifest.json, maps each phase to its analyzer, dispatches. Harness never calls subagents directly. `agents/{redteam-recon-analyzer.md, redteam-evasion-analyzer.md, redteam-extraction-analyzer.md, redteam-report-generator.md}` (opus). Prompt templates under `skills/adversarial-ml-redteam/references/prompts/`.
**REFACTOR**: Extract common rubric into `knowledge/redteam-rubric.md`
**Files**: `agents/redteam-*.md`, `skills/adversarial-ml-redteam/references/prompts/*.md`, `evals/redteam-report/{fixtures/,rubric.md}`
**Commit**: `feat(security-review): red-team analysis agents + report`

#### Step 19: /export-pdf command

**Complexity**: trivial
**RED**: `pandoc` and `weasyprint` both absent → exits 0 with skip. Either present → PDF produced; absolute path printed.
**GREEN**: `commands/export-pdf.md` shells to available tool. Default CSS in `templates/report-css/default.css`.
**REFACTOR**: None
**Files**: `commands/export-pdf.md`, `templates/report-css/default.css`
**Commit**: `feat(security-review): /export-pdf optional report export`

### Phase D — Integration

#### Step 20: Registry + release-please + final audit

**Complexity**: standard
**RED**: `/agent-audit` passes both plugins; structure-parity passes; `/agent-eval` passes all fixtures (tier-1 mocks + tier-2 integration in nightly); `shellcheck`, `ruff`, `pytest` clean; marketplace local-install of both plugins verified; release-please per-plugin bumps verified (`feat(security-review):` bumps only companion).
**GREEN**: Update `knowledge/agent-registry.md`, both CLAUDE.md registry tables, slash-command registry. Configure `release-please-config.json` for per-plugin component versioning.
**REFACTOR**: None
**Files**: both CLAUDE.md, `knowledge/agent-registry.md`, `.claude-plugin/marketplace.json`, `release-please-config.json`, `.release-please-manifest.json`
**Commit**: `docs(security-review): register components + split release-please`

## Detailed implementation guidance from `opus_repo_scan_test` reference

This plan's structure mirrors a working reference (`opus_repo_scan_test-main`). The sections below lift concrete implementation details from that reference so Phase B/C implementers do not rediscover them. Each bullet is keyed to the step it informs.

### Step 3b ruleset coverage — add `crypto-anti-patterns.yaml`

Reference `scan-07` catches a specific crypto anti-pattern class our rulesets do not currently cover. Ship a fourth custom semgrep ruleset `knowledge/semgrep-rules/crypto-anti-patterns.yaml` alongside ml-patterns / llm-safety / fraud-domain. Patterns to include:

- `NODE_TLS_REJECT_UNAUTHORIZED=0` literal or env assignment
- `--openssl-legacy-provider` flag in any invocation
- Non-AEAD ciphers (AES-CBC without HMAC, RC4, DES, 3DES) in crypto call sites
- pip `trusted-host` wildcards (`*.domain.tld`, bare `*`) in requirements files or install commands
- Passphrase reuse across env files (covered by `entropy-check.py` cross-env reuse, but also flag in semgrep for single-file cases)

Each pattern ships with a positive + negative fixture under `evals/semgrep-rulesets/crypto-anti-patterns/`.

### Step 6 — ACCEPTED-RISKS as universal agent-level invariant

Reference requires every detection agent to read `business_logic.md` before emitting findings. Add the same universal invariant to `plugins/agentic-security-review/CLAUDE.md` (and echo in `plugins/agentic-dev-team/CLAUDE.md`): "every detection agent consults `ACCEPTED-RISKS.md` at the repo root before emitting findings; items matched by a rule are suppressed with a logged audit entry, not omitted silently."

Applies to: `security-review`, `domain-review`, `business-logic-domain-review`, `tool-finding-narrative-annotator`, static-analysis adapters, and any future detection agent.

### Step 14 — exec-report output structure, severity framework, and enforcement invariants

**Per-repo + cross-repo output structure.** When `/security-assessment` runs against multiple target paths (directories passed as separate arguments, or a single path containing repo subdirectories named in a manifest), the exec report generator emits one report per repo plus a cross-repo summary — matching the reference's four-document pattern. For single-repo assessments, a single report is emitted. Filename convention: `<repo-name>-security-assessment.md` + `cross-repository-security-summary.md`.

**Severity framework mapping (presentational).** The unified finding envelope uses a lint-grade severity scale (`error | warning | suggestion | info`). The exec report maps these into a presentational CRITICAL/HIGH/MEDIUM/LOW scale via the mapping table published in `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` (added in contract v1.1.0).

**Invariants enforced by exec-report-generator** (reject findings from the report with a named error if violated):

- Every CRITICAL or HIGH finding must carry a CWE (the primitives contract makes CWE strongly recommended at the schema level; the report-generator enforces).
- Every CRITICAL or HIGH finding must carry a reachability trace (from the disposition register's `reachability.rationale`). If reachability_source is `llm-fallback`, the Section 0 banner per Phase B Step 14's existing AC is emitted.
- Dedup before reporting: one credential appearing in N config variants is one finding with N locations.

### Step 15 — harness `config.py`, failure handling, scoring library

**Environment variable config.** `config.py` supports the following env-var overrides (names chosen to match the reference for operator muscle memory):

| Env var | Default | Purpose |
|---|---|---|
| `TARGET_URL` | none; required | Base URL of the model service |
| `MODEL_ENDPOINT` | `/1_0/predict` | Model path appended to `TARGET_URL` |
| `RATE_LIMIT` | `5` | Maximum requests per second |
| `REQUEST_TIMEOUT` | `30` | Per-request timeout in seconds |
| `QUERY_BUDGET` | `10000` | Hard stop across all scripts combined |
| `MAX_RETRIES` | `3` | Retries on 5xx, timeout, or connection error |

Derived URLs (`PREDICT_URL`, `PAYLOAD_URL`, `VERSION_URL`) are built from `TARGET_URL + MODEL_ENDPOINT` and used directly by probes.

**Failure handling.** A failed probe does NOT halt the pipeline — the orchestrator logs the failure and continues to the next probe (best-effort). Dependents of a failed probe run without their expected input; the per-probe summary table at the end of the run names missing inputs. Reference pattern: failures are data, not exceptions.

**Scoring library.** `harness/redteam/lib/scoring.py` provides:

- `extract_score(response) -> float | None` — normalizes fraud / probability scores across response shapes:
  - top-level float (`{"score": 0.92}` or raw `0.92`)
  - common keys: `score`, `fraud_score`, `probability`, `risk_score`
  - nested: `result.probas.B`, `predictions[0].score`, `output.confidence`
- `build_baseline_payload(features)` — constructs a mid-range payload for sensitivity / boundary analysis.

Scripts MUST use `extract_score` rather than parsing response bodies directly — this keeps the response-shape knowledge in one place.

### Step 16 — feature discovery four-step cascade (probe 02)

The schema-discovery probe tries discovery strategies in order until one succeeds:

1. Fetch `/openapi.json` or `/swagger.json`; parse the schema for request body properties.
2. GET the `PAYLOAD_URL` endpoint (some ML services expose this); parse the response keys.
3. POST an empty payload, mine the error response for field names (`"field X is required"`, `"missing property Y"`, schema-validation error envelopes).
4. Brute-force against `lib/feature_dict.py` — a curated ~200-entry list of common fraud-detection feature names organized by category (transaction, card_account, merchant, temporal, geolocation, velocity_aggregates, device_digital, risk_indicators, client_routing, authentication). Try each feature individually; retained if the response changes compared to a baseline.

Record which strategy succeeded in the probe's output so downstream probes know whether they're working from an authoritative schema or a best-effort reconstruction.

### Step 17 — attack methods (probes 05, 07)

**Evasion (probe 05).** Combine three methods in order of cost:

1. **Random search** — sample N random payloads around the decision boundary; keep the lowest-scoring fraud-like instances. Fast, wide coverage.
2. **Greedy perturbation** — starting from a fraud-labeled baseline, iteratively modify the most-sensitive feature (from probe 03's ranking) until the score flips. Cheap, local.
3. **`scipy.optimize.differential_evolution`** — global optimization over the feature space with a custom objective that rewards low score + input realism. Expensive; run only if (1) and (2) fail to find realistic adversarials.

Each method's results are tagged in the output so analysts can reason about which attack class succeeded.

**Surrogate extraction (probe 07).** Use Latin-Hypercube sampling over the feature space to generate ~2-5K query points. Train three surrogate models against the captured scores:

- Decision tree (depth ≤ 8) — interpretable; extracts rule-like decision structure
- Random forest (100 trees) — robust to noise; better R²
- Linear regression — sanity baseline

Report **R² on a held-out 20% of samples** as the extraction fidelity metric. R² > 0.85 indicates the model has been substantially reproduced locally; > 0.95 is effectively IP theft.

### Step 19 — PDF CSS starting point

`templates/report-css/default.css` seed values (from reference's embedded CSS):

- A4 page size, 2cm × 1.5cm margins
- Page footer: `CONFIDENTIAL — [project]` (center) + `Page N of M` (right)
- H1 underline + blockquote border: red accent (`#c00`)
- Zebra-striped tables
- Monospace code blocks; `codehilite` Markdown extension for syntax highlighting
- Muted colour scheme; no decorative graphics

These are starting values — projects can override via their own stylesheet if the `--css <path>` flag is passed to `/export-pdf`.

### Consistency invariants (lifted from reference's § "Consistency invariants")

Every finding before it reaches the exec report:

- Has `file` + `line` — enforced by unified finding schema (required fields).
- Has CWE when severity is `error` or `warning` — enforced by exec-report-generator per Step 14 invariants.
- CRITICAL / HIGH findings have a reachability trace — enforced by exec-report-generator.
- Deduplication applied — credential-in-N-variants → one finding with N locations.

Breaking any of these makes the exec report unreliable; the reference's experience is that enforcement is needed, not convention.

## Complexity Classification

| Rating | Criteria | Review depth |
|--------|----------|--------------|
| `trivial` | Config, docs, single-file wrapper | Skip inline review |
| `standard` | New function/test/module in existing pattern | Spec-compliance + quality |
| `complex` | Architectural, security-sensitive, cross-cutting, new abstraction | Full agent suite |

## Pre-PR Quality Gate

- [ ] All tier-1 (mock) eval fixtures pass `/agent-eval`
- [ ] Tier-2 (real-binary) eval suite passes in nightly CI
- [ ] `/agent-audit` passes both plugins
- [ ] `shellcheck` clean; `ruff` + `pytest` clean on Python
- [ ] `/code-review` passes all new files
- [ ] Primitives contract conformance fixture passes
- [ ] SARIF schema validation passes on all SARIF-emitting adapters + custom scripts
- [ ] Semgrep custom rulesets each have passing positive + negative fixtures
- [ ] PostToolUse hook registered in agentic-security-review only (not agentic-dev-team); opt-out eval passes
- [ ] PreToolUse contract-version-guard blocks unversioned edits; bypass path for release-please verified
- [ ] Consent gate + scope enforcement tests pass; public targets refused by default
- [ ] Per-plugin release-please produces independent version bumps
- [ ] Adapter Maintenance Policy documented in skill frontmatter
- [ ] Structure Contract satisfied; omissions documented

## Risks & Open Questions

- **Tool install footprint**: ~18 tools. Install guide in companion plugin's CLAUDE.md names commands per tool, grouped by capability tier. A `scripts/install-tools.sh` convenience script may follow.
- **SARIF drift**: adapter Maintenance Policy mitigates via tier-2 CI. Residual risk: if multiple tools drift simultaneously, batch update required.
- **Semgrep ruleset currency**: community rulesets updated via `semgrep --config auto` periodically; custom rulesets maintained by us. Policy documented in skill.
- **joern install weight**: ~400MB. Graceful fallback + fallback-mode banner in exec report ensures transparency. Optional `memory/joern-cache/<sha>.cpg` caches reduce rebuild time.
- **Context cost**: tool outputs + RECON + disposition register could breach 40% ceiling on large repos. Mitigation: pass only finding IDs + file paths to LLM agents; agents re-read on demand.
- **Compliance mapping accuracy**: LLM edge-case annotations are informational; disclaimer on every report header.
- **Target-scope broadening**: private-CIDR + self-cert is the v1 boundary. Legal-review checkpoint required before loosening.
- **Plugin dependency semantics**: if `plugin.json` lacks `depends_on`, rely on `install.sh` runtime check.
- **Hook opt-out durability**: `settings.local.json` override is the documented path; opt-out eval verifies enforcement.
- **FP-reduction graduation to agentic-dev-team**: deferred to post-ship stabilization under minor contract bump.

## Plan Review Summary

Four plan review personas ran across six revision cycles. Final verdicts on revision 6:

| Reviewer | Final verdict | Iterations |
|----------|---------------|-----------|
| Acceptance Test Critic (QA) | approve | 3 |
| Design & Architecture Critic | approve | 3 |
| UX Critic | approve | 4 |
| Strategic Critic | approve | 3 |

### Revisions by round

**Rev 2 — restrict + contract + harness placement:**
- Red-team scope restricted to self-owned targets (localhost + RFC1918 + ::1); public targets require `--self-certify-owned` + SHA-256 logged
- Primitives contract file added with semver versioning + install-time version check + CI conformance fixture
- Python harness relocated from `skills/.../scripts/` to plugin-level `harness/`
- FP-reduction moved from agentic-dev-team to companion plugin
- Structure Contract revised: "same schema where applicable; omitted dirs documented"

**Rev 3 — consent & test determinism:**
- Exact consent-gate refusal message text published in acceptance criteria
- `results/progress-manifest.json` + "Resume with --start <phase>" message for mid-run failures
- `install.sh` emits actionable missing-dep messages
- Injectable mock clock specified; Gherkin referenced it explicitly
- Step pipeline assertions split to avoid forward dependencies

**Rev 4 — architectural pivot to tools-first:**
- ~20 security tools added via static-analysis-integration
- PostToolUse auto-scan hook on Edit/Write
- FP-reduction made hybrid (joern + LLM fallback)
- Pattern-first compliance mapping
- Custom shipped scripts (entropy-check, model-hash-verify, service-comm-parser, shared-cred-hash-match)

**Rev 5 — SARIF-first + hook-in-companion:**
- SARIF-first tool orchestration: shared SARIF parser + thin per-tool adapters; unified finding envelope narrowed to SARIF `result` fields
- PostToolUse hook moved from agentic-dev-team to agentic-security-review (security plugin only)
- Adapter Maintenance Policy documented with update trigger + deprecation path
- Release-please bypass path for contract-version-guard
- Tier-1 (mock) + tier-2 (real-binary nightly) CI split for tool adapters
- Custom semgrep rulesets shipped: `ml-patterns.yaml`, `llm-safety.yaml`, `fraud-domain.yaml`
- LLM call-counter interface specified; Mermaid comparison mechanism specified
- Byte-equal Mermaid pass-through assertion; fallback-mode banner in exec report Section 0

**Rev 6 — policy completeness + MVP core:**
- Step 3 split into 3a (required-5 baseline; MVP Core) and 3b (optional + rulesets + custom scripts + tier-2 CI)
- Ruleset Maintenance Policy added: quarterly cadence, FP-drift threshold, community-PR intake, deprecation after two stale cycles
- `maintainers:` frontmatter (min 2) replaces single-maintainer with 14-day escalation
- `trufflehog` moved to SARIF tier (v3 supports `--output sarif`); `govulncheck` correctly labeled as permanent bespoke adapter
- "bespoke-JSON adapter" replaces "legacy JSON adapter"; tier-implementation labels confirmed internal-only
- Install output distinguishes required tools (`[REQUIRED]` prefix, hard-fail on absence) from optional (warning-only)
- LLM-safety coverage claim bounded: "intentionally narrow — not a substitute for runtime LLM safety testing"; acceptance criterion requires verbatim appearance in CLAUDE.md + README
- MVP Core steps labeled: 1, 3a, 8, 9, 13

### Strategic architectural decisions embedded in the plan

- **Tools-first, LLM for semantic reasoning only.** Deterministic tools handle detection; LLM agents handle business-logic, narrative annotation, cross-repo attack chains, executive prose, and judgment stages of FP-reduction.
- **SARIF-first output normalization.** OASIS standard; free downstream integration; eliminates ~70% bespoke parser maintenance. Bespoke-JSON adapters only where SARIF genuinely unavailable upstream.
- **Hooks default ON in security plugin only.** Not ambient for general `agentic-dev-team` users.
- **Self-owned targets only for red-team.** Three-layer enforcement: command scope check + orchestrator env-var assertion + PreToolUse hook. Public targets require explicit self-certification artifact whose SHA-256 is logged.
- **Graceful degradation.** Every tool absence is a warning, not a failure. Joern-absent FP-reduction falls back to LLM with a transparent fallback-mode banner in the exec report.
- **Versioned primitives contract.** Cross-plugin interface stable under semver; install-time check + CI conformance fixture + PreToolUse authoring guard prevent silent breakage.
