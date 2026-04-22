---
name: static-analysis-integration
description: >-
  SARIF-first pre-pass stage for /code-review that runs available static
  analysis tools and normalizes their output to the unified finding envelope
  defined in security-primitives-contract v1.0.0. Deduplicates findings across
  tools and passes confirmed issues to AI agents so they can focus on semantic
  concerns.
role: worker
user-invocable: false
version: 2.0.0
maintainers:
  - bdfinst
  - unassigned   # TODO: name a second maintainer before shipping to production; bus-factor minimum is 2.
required-primitives-contract: ^1.0.0
---

# Static Analysis Integration (SARIF-first)

## Overview

This skill defines the static-analysis pre-pass. When enabled, it runs
deterministic analysis tools before AI review agents, collecting structured
findings that agents receive as pre-confirmed context. This reduces token
waste on syntactic issues and lets agents focus on semantic and architectural
concerns.

**Output contract**: every finding, regardless of source tool, is normalized
to the **unified finding envelope v1.0** defined in
`plugins/agentic-dev-team/knowledge/security-primitives-contract.md`. The
shared SARIF parser handles the 80% of modern tools that emit SARIF natively;
thin per-tool adapters wrap the handful that don't.

## Constraints

1. Collect and report findings only — the skill reads source files and tool
   output but makes no code edits.
2. Graceful degradation: if no tools are installed, return an empty result
   with `status: skip`; absence is never a pipeline failure.
3. Deduplicate across tools: the same issue reported by multiple tools
   appears once, attributed to the higher-priority source.

## Tool tiers

### Tier 1 — required baseline (5 tools, SARIF native)

These five tools are the `/code-review` baseline. All emit SARIF natively and
pass through the shared SARIF parser unchanged.

| Tool | SARIF invocation | Capability tier |
|---|---|---|
| semgrep | `semgrep scan --sarif --config auto` | SAST |
| gitleaks | `gitleaks detect --report-format sarif --report-path -` | secrets |
| trivy | `trivy config --format sarif <path>` + `trivy fs --format sarif <path>` | IaC + supply-chain |
| hadolint | `hadolint --format sarif <Dockerfile>` | IaC (Dockerfile) |
| actionlint | `actionlint -format '{{range $err := .}}{{...}}{{end}}'` → SARIF adapter | CI-CD |

actionlint's SARIF output is via a thin wrapper — the binary emits JSON that
an adapter maps to SARIF `result` shape in 10-15 LOC. See
`references/tool-configs.md` for the adapter script.

### Tier 2 — optional SARIF adapters

Shipped in P2 Step 3b. Not part of the baseline. See that step's documentation.

### Tier 3 — bespoke JSON adapters

Shipped in P2 Step 3b for tools that don't yet support SARIF upstream. Kept
narrowly scoped; each adapter is ≤ 40 LOC.

### Tier 4 — legacy (pre-SARIF, preserved for compatibility)

ESLint / tsc / pylint remain callable via their native JSON outputs when
invoked by older flows. They are **not** part of the Step 3a baseline and
will be migrated to SARIF adapters if/when upstream support lands.

## Execution flow

### 1. Detect available tools

For each Tier 1 tool, run a short detection command (`command -v <tool>`).
Record presence in a tool-map. Report missing Tier 1 tools as a **warning
group** in the install-hint format below, never a pipeline failure.

If no Tier 1 tools are present, return:

```json
{ "status": "skip", "tools": [], "findings": [], "summary": "No static analysis tools detected." }
```

### 2. Run available tools in parallel

Dispatch each available tool's invocation. Each returns SARIF on stdout (or
via its adapter). Collect SARIF documents keyed by tool name.

**Target walk MUST include CI/CD workflow files.** Some scanners (actionlint,
trivy) work on files under `.github/workflows/` that sit OUTSIDE a repo's
`src/` tree. When walking a target path, include:

- `.github/workflows/*.{yml,yaml}` (GitHub Actions)
- `.gitlab-ci.yml` + `.gitlab/**/*.{yml,yaml}` (GitLab CI)
- `.circleci/config.yml` (CircleCI)
- `azure-pipelines.yml` + `.azure-pipelines/**/*.{yml,yaml}` (Azure Pipelines)
- `bitbucket-pipelines.yml`
- `Jenkinsfile` + `jenkinsfile.d/**/*` (Jenkins declarative)

These are in-scope for scan-06 (CI/CD pipeline security). Every Tier-1 tool
that can process them should be invoked on them — actionlint for GitHub
Actions, trivy-config for any CI YAML, semgrep with `p/github-actions` (or
the bundled `crypto-anti-patterns.yaml` rule that catches `printenv` in
workflow `run:` blocks).

A target path whose CI files live OUTSIDE the walked tree (e.g. a monorepo
where `.github/workflows/` is at the repo root but the target is a
subdirectory) MUST still walk up to the repo root to find them. Record in
the returned result which CI directories were scanned:

```json
{
  "ci_dirs_scanned": [".github/workflows", ".gitlab-ci.yml"],
  ...
}
```

If no CI files were found, record `"ci_dirs_scanned": []` — the caller can
then surface "no CI files in scope" as a Top 3 Actions item when a CI config
would be expected.

### 3. Normalize to unified finding envelope

The shared SARIF parser (`references/sarif-parser.md`) walks each SARIF
document's `runs[*].results[*]` and emits one unified finding per result,
mapping fields as follows:

| SARIF path | Unified finding field | Notes |
|---|---|---|
| `results[*].ruleId` | `rule_id` | Prefixed with tool name: `<tool>.<lang?>.<rule>` |
| `results[*].locations[0].physicalLocation.artifactLocation.uri` | `file` | Repo-relative POSIX path |
| `results[*].locations[0].physicalLocation.region.startLine` | `line` | 1-indexed |
| `results[*].locations[0].physicalLocation.region.startColumn` | `column` | 1-indexed, optional |
| `results[*].level` | `severity` | `error`→`error`, `warning`→`warning`, `note`→`suggestion`, `none`/absent→`info` |
| `results[*].message.text` | `message` | Truncated to 500 chars |
| `runs[*].tool.driver.rules[ruleIndex].properties.cwe` | `cwe[]` | If present, populate as `["CWE-N"]` |
| `runs[*].tool.driver.name` | `metadata.source` | e.g. `"semgrep"` |
| result-level `properties.confidence` | `metadata.confidence` | Default `medium` if absent |

The parser MUST validate each emitted finding against the unified-finding-v1
schema before returning; a schema violation fails the run with a named tool
+ rule id.

### 4. Deduplicate

Two findings are duplicates if they share `file`, `line`, and either (a)
identical `rule_id`, or (b) `message` fuzzy-matches (cosine similarity > 0.85
on the normalized message text). When duplicates exist, keep the one from
the higher-priority tool by this order:

```
semgrep > gitleaks > trivy > hadolint > actionlint > (legacy ESLint > tsc > pylint)
```

### 5. Consult ACCEPTED-RISKS.md

If `ACCEPTED-RISKS.md` is present at the repo root, apply suppression per
`plugins/agentic-dev-team/knowledge/accepted-risks-schema.md`. Suppressed
findings are removed from the return value but logged to the audit trail.

### 6. Return structured result

```json
{
  "status": "pass|warn|fail",
  "tools_available": ["semgrep", "hadolint"],
  "tools_missing": [
    { "tool": "gitleaks", "install_hint": "gitleaks — secrets detection. install: brew install gitleaks" }
  ],
  "findings": [ /* unified finding envelope v1.0 objects */ ],
  "summary": "12 findings from 2 tools: 3 errors, 7 warnings, 2 suggestions"
}
```

`status`:
- `fail` if any finding has `severity: error`
- `warn` if warnings only
- `pass` if no findings OR no tools available

## Install-hint format

Consistent across every Tier 1 / Tier 2 / Tier 3 / Tier 4 tool:

```
<tool-name> — <capability-tier>. install: <package-manager> install <name>
```

Example rows:

```
semgrep — SAST. install: pip install semgrep
gitleaks — secrets detection. install: brew install gitleaks
trivy — IaC + supply-chain scanning. install: brew install trivy
hadolint — Dockerfile linting. install: brew install hadolint
actionlint — GitHub Actions linting. install: brew install actionlint
```

Install-hints are printed grouped by capability tier (secrets / IaC / CI-CD /
supply-chain / SAST / data-flow) in the install output. Tier-implementation
labels ("SARIF adapter", "bespoke-JSON adapter", "legacy") are internal
maintenance vocabulary and never surface in user-facing text.

Required tools carry a `[REQUIRED]` prefix; optional tools do not. Absence of
a required tool is a hard failure at install time; absence of an optional
tool is a warning.

## Adapter Maintenance Policy

Adapters (SARIF wrappers, bespoke JSON adapters) have a lifecycle independent
of the tools they wrap.

- **Owners**: this skill's frontmatter `maintainers:` list. Minimum 2 names.
- **Update trigger**: a tier-2 CI job (nightly) runs each adapter against the
  installed tool binary. Any schema drift that breaks the adapter fails CI
  and opens an auto-issue tagged `adapter-drift`.
- **Escalation**: a tier-2 failure unassigned for > 14 days escalates to
  CODEOWNERS.
- **Deprecation**: an adapter failing CI for three consecutive releases AND
  upstream unmaintained for > 6 months is demoted to "deprecated" — still
  shipped, emits a warning on invocation, and is removed in the next MAJOR
  contract version.
- **Adding a tool**: requires (a) a fixture pair under
  `evals/static-analysis-tools/tier1-mocks/<tool>/` (mock output + expected
  unified finding), and (b) a SARIF adapter first; bespoke-JSON only if
  upstream genuinely has no SARIF plan.

## Ruleset Maintenance Policy

Separate lifecycle from adapters — rulesets track evolving attack patterns,
not tool schema drift.

- **Owners**: each custom ruleset (`knowledge/semgrep-rules/*.yaml`) has a
  `maintainers:` frontmatter block with ≥ 2 names.
- **Review cadence**: quarterly — reviewers confirm patterns are still
  relevant, add new attack signatures, retire deprecated ones.
- **FP drift threshold**: if eval fixtures show > 20% false-positive noise on
  the tier-2 suite, the ruleset is paused and triaged within one release.
- **Community-PR intake**: PRs adding patterns require a positive fixture
  plus a negative fixture. Rejections must cite the policy.
- **Deprecation**: a ruleset with no review or change in two consecutive
  review cycles is demoted to "archived" unless a maintainer re-ups.

## Agent context injection

When findings are passed to review agents, format them so agents don't
re-report confirmed static findings and can focus on semantic concerns:

```text
## Static Analysis Pre-Pass Results

The following issues were detected deterministically by static analysis.
Do not re-report these issues. Focus your review on semantic and
architectural concerns that static analysis cannot detect.

| Tool | Severity | File | Line | Rule | Message |
|------|----------|------|------|------|---------|
| semgrep | error | src/api/handler.ts | 42 | javascript.express.audit.xss | Potential XSS |
| gitleaks | error | .env.example | 3  | generic.aws-access-key | AWS key pattern in committed file |
```

If no findings exist: "Static analysis pre-pass ran (tools: semgrep,
hadolint). No findings — all clear."

This context goes to **all** review agents, not just security-review.

## Related

- `references/tool-configs.md` — per-tool invocation commands, adapter
  scripts, and install hints
- `references/sarif-parser.md` — normalized mapping from SARIF `result` to
  unified finding envelope v1.0
- `evals/static-analysis-tools/tier1-mocks/` — tier-1 mocked SARIF fixtures
  for the 5 baseline tools
- `evals/static-analysis-tools/tier2-integration/` — tier-2 real-binary
  integration tests (run in nightly CI, not on every PR)
- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` —
  unified finding envelope v1.0 definition
- `plugins/agentic-dev-team/knowledge/accepted-risks-schema.md` —
  per-project suppression policy
