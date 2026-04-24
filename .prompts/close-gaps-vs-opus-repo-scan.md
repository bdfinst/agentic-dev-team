You are working in the `agentic-security-assessment` plugin at
/Users/finsterb/_git-os/agentic-dev-team/plugins/agentic-security-assessment/

Your task: close specific capability gaps identified by comparison with a
reference security-assessment harness at
/Users/finsterb/Downloads/opus_repo_scan_test-main/ (read-only reference).

## Ground rules

- This plugin is intentionally **tool-first** (SARIF from semgrep/gitleaks/
  trivy/hadolint/actionlint feeding LLM judgment agents). Do NOT convert it
  into a prompt-driven clone of the reference. New coverage must prefer
  deterministic scanners + rules first, and add LLM agents only where
  judgment is required.
- The plugin follows the shared-primitives contracts in the sibling
  `agentic-dev-team` plugin (unified-finding envelope v1.0.0, severity
  mapping v1.1.0, disposition-register, RECON envelope). Any new finding
  producer must emit into that envelope. Do not invent parallel schemas.
- Work one gap at a time. Stop for review after each. Follow
  `CLAUDE.md` discipline for this plugin.

## Gaps to close (priority order)

### 1. Concurrency / state-safety coverage (largest detection gap)

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/agents/scan-09-concurrency-state.md`
and `plan_01.md:72-76`. Covers: JS global-variable races (e.g., module-level
`let` mutated per-request in Express/Fastify handlers), Cassandra TOCTOU
(read-then-write without LWT), consistency-level mismatches (QUORUM read /
ONE write for authz data), missing circuit breakers on downstream calls,
double-spend / retry-replay patterns in fraud scoring.

Acceptance:
- Semgrep ruleset at `knowledge/semgrep-rules/concurrency-state.yaml` with
  rules for the patterns above. Rule IDs follow the existing naming scheme.
- An `agents/concurrency-review.md` agent that runs AFTER static SARIF
  produces findings for this category — it inspects call graphs and request
  lifetimes to reduce FPs (e.g., confirming a `let` is actually mutated in
  a request handler vs only at startup).
- Wire into the Phase 1 fan-out in `skills/security-assessment-pipeline/SKILL.md`.
- Update `docs/comparative-testing.md:45` row from TBD to implemented,
  including an equivalence fixture under `evals/comparative/` covering at
  minimum: one module-level-mutable-state race, one missing-LWT TOCTOU,
  one consistency-level mismatch, one missing circuit breaker.

### 2. Git-history secrets pass

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/agents/scan-01-secrets-credentials.md:47-53`
— runs `git log --all --full-history -- "*password*" "*secret*" "*.pem"`
etc. to find credentials that were committed and later removed (but are
still in history and the tree snapshot in pack files).

Acceptance:
- New tool at `harness/tools/git-history-secrets.py` (or a gitleaks
  `--log-opts "--all --full-history"` wrapper if that covers the cases).
  Must emit SARIF into the unified-finding envelope.
- Added as a tier-1 secrets detector alongside gitleaks + entropy-check,
  not a replacement. Dedup against current-tree gitleaks hits via the
  existing cross-tool priority dedup in `static-analysis-integration`.
- Findings reference the commit SHA in `source_ref` so reviewers can
  confirm historical vs current exposure.

### 3. Red-team analyzer coverage parity

Reference red-team pipeline has 5 interpretation prompts (see
`/Users/finsterb/Downloads/opus_repo_scan_test-main/adversarial-agents/prompts/`
and `docs/adversarial-pipeline.md`). This plugin ships 4. Close two gaps:

a. **Probe-02 schema-discovery analyzer.**
   Reference: `adversarial-agents/prompts/adversarial-02-schema.md` —
   produces a feature inventory categorized by: transaction attributes,
   card attributes, merchant attributes, temporal, geolocation, velocity,
   device fingerprint, risk scoring inputs, routing, authentication.
   For each category: exposure level (what the endpoint accepts), drift
   detection sensitivity (if probed), and exploitation potential.

   Acceptance: new `agents/redteam-schema-analyzer.md` that consumes the
   probe-02 JSON from `harness/redteam/results/02_schema_discovery.json`
   and emits a feature-inventory narrative to the red-team report. Wire
   it into `commands/redteam-model.md`.

b. **Probe-06 input-validation analyzer.**
   Reference: `adversarial-agents/scripts/06_input_validation.py` output
   is interpreted in `adversarial-05-report.md`. Create a dedicated
   analyzer (not just inclusion in the final report) that flags
   fail-open behavior, error-message information leakage, and type
   confusion / coercion vulnerabilities specifically.

   Acceptance: new `agents/redteam-input-validation-analyzer.md`, wired
   into `commands/redteam-model.md`, output feeds
   `redteam-report-generator`.

### 4. Per-endpoint auth/authZ matrix artifact

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/agents/scan-02-authn-authz.md`
emits a per-endpoint table (endpoint, method, auth required?, authZ
check present?, roles enforced, notes).

Acceptance:
- `harness/tools/auth-matrix-extractor.py` that consumes RECON's
  `security_surface.auth_paths` plus the target's route definitions and
  emits a JSON + Markdown table. Feeds the exec report as a new
  Section 3c or a new Appendix F.
- `security-review` agent annotates each row with "missing authZ",
  "anonymous by design (see ACCEPTED-RISKS)", or "OK".

### 5. Cross-repo compliance audit table + risk matrix

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/agents/analyze-10-cross-repository.md`
§4 (PCI-DSS/GDPR requirement-by-requirement table across repos) and
§5 (consolidated severity-dimension × repo risk matrix, e.g. rows =
{Secrets, AuthZ, PII, Crypto, Supply Chain, ...}, cells = worst severity
found in that dimension in that repo).

Acceptance:
- Extend `agents/cross-repo-synthesizer.md` to produce both tables.
- Exec report `agents/exec-report-generator.md` Section 3b (multi-repo
  only) renders them. Mandatory informational-not-audit-grade disclaimer
  remains.

### 6. Forbid tree re-walks in LLM agents

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/CLAUDE.md:63-65`:
"Don't re-walk the directory tree in scan agents 01–09. They must consume
the RECON manifest. If a scan agent reads a file not in the manifest, it
must flag the addition."

Acceptance:
- Add an equivalent invariant to this plugin's `CLAUDE.md` scoped to the
  LLM agents (`security-review`, `business-logic-domain-review`,
  `fp-reduction`, `cross-repo-synthesizer`, analyzers). Deterministic
  tools are exempt — they intentionally walk.
- Add a `hooks/recon-manifest-check.sh` PreToolUse hook that warns when
  an LLM agent Reads a file not in the active RECON manifest. Warn-only,
  not blocking.

### 7. Fill in the 11 TBD component-equivalence unit tests

Reference: `docs/comparative-testing.md:34-48` in THIS plugin.
Only `codebase-recon-equivalence.md` is implemented; 11 are TBD.

Acceptance: one equivalence fixture per row, each with a ground-truth
YAML naming the findings the reference scan produces, and a pass/fail
criterion for this plugin's equivalent producer. Do them in the same
priority as the rows are listed.

### 8. In-plugin turnkey fixture

Reference: `/Users/finsterb/Downloads/opus_repo_scan_test-main/RUN-FIXTURE.md`
is a single paste-and-run workflow with fixture repos in-tree at `repos/`.

Acceptance:
- `docs/RUN-FIXTURE.md` in this plugin with a single-command entrypoint
  that runs the full pipeline against a bundled minimal fixture
  (committed under `evals/fixture/` or similar), with expected runtime
  and expected finding counts per category.
- The fixture must exercise at least one finding from each of the nine
  reference concern areas (secrets, authZ, business-logic, PII, infra,
  CI/CD, crypto, supply chain, concurrency).

## Deliverable protocol

1. Before touching code, read the reference files cited in each gap and
   write a short plan for that gap (files to add/modify, acceptance
   evidence). Present the plan. Wait for approval.
2. Implement in the red-green-refactor order defined by this plugin's
   CLAUDE.md.
3. After each gap, run the equivalence test for that gap (create it if
   missing — see gap 7) and the existing `/code-review` before presenting
   for review.
4. Do not batch gaps. One gap → one review cycle → next gap.
