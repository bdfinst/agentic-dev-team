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

Maintenance policies for adapters and rulesets live in `maintenance.md` — those are out-of-runtime concerns.

## Constraints

1. Collect and report only — read source and tool output; make no code edits.
2. Graceful degradation: if no tools are installed, return `status: skip`; absence is never a pipeline failure.
3. Deduplicate across tools: the same issue reported by multiple tools appears once, attributed to the higher-priority source.

## Tool tiers

### Tier 1 — required baseline (SARIF native)

| Tool | SARIF invocation | Capability |
|---|---|---|
| semgrep | `semgrep scan --sarif --config auto` | SAST |
| gitleaks | `gitleaks detect --report-format sarif --report-path - --no-verify` | secrets |
| trivy | `trivy config --format sarif --skip-update --offline-scan <path>` + `trivy fs --format sarif --skip-update --offline-scan <path>` | IaC + supply-chain |
| hadolint | `hadolint --format sarif <Dockerfile>` | IaC (Dockerfile) |
| actionlint | binary emits JSON; thin adapter maps to SARIF `result` (see `references/tool-configs.md`) | CI/CD |
| pmd | `pmd check -d . -R <resolved-ruleset> -f sarif --no-progress` — language-conditional: dispatched (and hinted when missing) only when `.java` files are in the target set; detection probes the repo-local `.pmd/` bin before PATH; ruleset resolution in `references/tool-configs.md` | Java code quality |

### Tier 2 — optional SARIF adapters

Shipped in P2 Step 3b. Not part of the baseline.

### Tier 3 — bespoke JSON adapters

Shipped in P2 Step 3b for tools without upstream SARIF. Each adapter ≤ 40 LOC. A thin adapter normalizes `security-review` agent output into the unified envelope (see `adapters/security-review-adapter.py`). Rule_id lookup is driven by `plugins/dev-team/knowledge/security-review-rule-map.yaml`; malformed categories hard-fail, well-formed-but-unmapped categories fall back to `security-review.*` with a WARN.

### Tier 4 — legacy (pre-SARIF)

ESLint / tsc / pylint remain callable via native JSON for older flows. Not part of the Step 3a baseline; migrate to SARIF when upstream lands.

## Execution flow

### 1. Detect available tools

For each Tier 1 tool, run `command -v <tool>`. Record presence in a tool-map. Missing Tier 1 tools surface as a **warning group** via the install-hint format below — never a pipeline failure.

If no Tier 1 tools are present, return:

```json
{ "status": "skip", "tools": [], "findings": [], "summary": "No static analysis tools detected." }
```

### 1b. Offline enforcement (gitleaks, trivy)

These tools default to making network calls; in restricted-egress environments those calls hang or fail and take the pre-pass down with them. Both are pinned to local-only operation so the pre-pass never depends on outbound network access.

**gitleaks** runs with `--no-verify`. Verification (confirming a detected secret is a live credential) is the only outbound call gitleaks makes; disabling it keeps detection fully pattern-based and offline. No preflight needed — the flag is always on.

**trivy** runs with `--skip-update --offline-scan` on both `trivy config` and `trivy fs`. Before dispatching trivy, run the **offline DB preflight** against the local cache (`${TRIVY_CACHE_DIR:-$HOME/.cache/trivy}/db/trivy.db`):

| Local DB state | Action | Warning |
|---|---|---|
| absent | skip trivy | `trivy local DB missing — run: trivy image --download-db-only` |
| mtime age ≤ 7 days | run (fresh) | none |
| mtime age > 7 days | run anyway | `trivy DB is N days old — consider refreshing with: trivy image --download-db-only` |

`N` is the integer day count. The 7-day boundary is inclusive (exactly 7 days = fresh; strictly greater than 7 days = stale). A missing or stale DB is **never a hard pipeline failure** — it degrades to a skip or a warning, consistent with the graceful-degradation constraint.

### 2. Run available tools in parallel

Dispatch each available tool's invocation. Each returns SARIF on stdout (or via its adapter). Collect SARIF documents keyed by tool name.

**Target walk MUST include CI/CD workflow files** even when they live outside the walked tree (monorepo case — walk up to the repo root to find them):

- `.github/workflows/*.{yml,yaml}` (GitHub Actions)
- `.gitlab-ci.yml` + `.gitlab/**/*.{yml,yaml}` (GitLab CI)
- `.circleci/config.yml` (CircleCI)
- `azure-pipelines.yml` + `.azure-pipelines/**/*.{yml,yaml}` (Azure Pipelines)
- `bitbucket-pipelines.yml`
- `Jenkinsfile` + `jenkinsfile.d/**/*` (Jenkins)

Invoke every Tier-1 tool that can process them — actionlint for GitHub Actions, trivy-config for any CI YAML, semgrep with `p/github-actions` (or the bundled `crypto-anti-patterns.yaml` rule that catches `printenv` in workflow `run:` blocks).

Record which CI directories were scanned:

```json
{ "ci_dirs_scanned": [".github/workflows", ".gitlab-ci.yml"], ... }
```

If none found, record `"ci_dirs_scanned": []`. The caller can then surface "no CI files in scope" when a CI config would be expected.

### 3. Normalize to unified finding envelope

The shared SARIF parser (`references/sarif-parser.md`) walks each SARIF document's `runs[*].results[*]` and emits one unified finding per result:

| SARIF path | Unified finding field | Notes |
|---|---|---|
| `results[*].ruleId` | `rule_id` | Prefixed: `<tool>.<lang?>.<rule>` |
| `results[*].locations[0].physicalLocation.artifactLocation.uri` | `file` | Repo-relative POSIX |
| `results[*].locations[0].physicalLocation.region.startLine` | `line` | 1-indexed |
| `results[*].locations[0].physicalLocation.region.startColumn` | `column` | 1-indexed, optional |
| `results[*].level` | `severity` | `error`→`error`, `warning`→`warning`, `note`→`suggestion`, `none`/absent→`info` |
| `results[*].message.text` | `message` | Truncated to 500 chars |
| `runs[*].tool.driver.rules[ruleIndex].properties.cwe` | `cwe[]` | If present: `["CWE-N"]` |
| `runs[*].tool.driver.name` | `metadata.source` | e.g. `"semgrep"` |
| result-level `properties.confidence` | `metadata.confidence` | Default `medium` if absent |

The parser MUST validate each emitted finding against unified-finding-v1 before returning; schema violations fail the run with a named tool + rule id.

### 4. Deduplicate

Two findings are duplicates if they share `file`, `line`, and either (a) identical `rule_id`, or (b) `message` cosine similarity > 0.85 on normalized text. When duplicates exist, keep the higher-priority tool:

```
semgrep > gitleaks > trivy > hadolint > actionlint > (legacy ESLint > tsc > pylint)
```

### 5. Consult ACCEPTED-RISKS.md

If present at repo root, apply suppression per `plugins/dev-team/knowledge/accepted-risks-schema.md`. Suppressed findings are removed from the return value but logged to the audit trail.

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

`status`: `fail` if any finding has `severity: error`; `warn` if warnings only; `pass` if no findings or no tools available.

## Install-hint format

```
<tool-name> — <capability-tier>. install: <package-manager> install <name>
```

Examples:

```
semgrep — SAST. install: pip install semgrep
gitleaks — secrets detection. install: brew install gitleaks
trivy — IaC + supply-chain scanning. install: brew install trivy
hadolint — Dockerfile linting. install: brew install hadolint
actionlint — GitHub Actions linting. install: brew install actionlint
```

Print install-hints grouped by capability tier (secrets / IaC / CI-CD / supply-chain / SAST / data-flow). Required tools carry a `[REQUIRED]` prefix; absence of a required tool is a hard failure at install time, absence of an optional tool is a warning. Tier-implementation labels ("SARIF adapter", "bespoke-JSON adapter", "legacy") are internal vocabulary and never surface in user-facing text.

## Agent context injection

When findings are passed to review agents, format them so agents don't re-report confirmed static findings:

```text
## Static Analysis Pre-Pass Results

The following issues were detected deterministically by static analysis.
Do not re-report these issues. Focus on semantic and architectural concerns
that static analysis cannot detect.

| Tool | Severity | File | Line | Rule | Message |
|------|----------|------|------|------|---------|
| semgrep | error | src/api/handler.ts | 42 | javascript.express.audit.xss | Potential XSS |
| gitleaks | error | .env.example | 3  | generic.aws-access-key | AWS key pattern in committed file |
```

If no findings: "Static analysis pre-pass ran (tools: <list>). No findings — all clear."

This context goes to **all** review agents, not just security-review.

## Related

- `references/tool-configs.md` — per-tool invocation commands, adapter scripts, install hints; hosts the "Build-time lanes" registry for `/build`'s static self-heal pass
- `references/language-setup.md` — user-facing per-language setup guide for the build-time self-heal pass and this pre-pass
- `references/sarif-parser.md` — normalized mapping from SARIF `result` to unified finding envelope v1.0
- `evals/static-analysis-tools/tier1-mocks/` — tier-1 mocked SARIF fixtures
- `evals/static-analysis-tools/tier2-integration/` — tier-2 real-binary integration tests (nightly CI)
- `knowledge/security-primitives-contract.md` — unified finding envelope v1.0
- `knowledge/accepted-risks-schema.md` — per-project suppression policy
- `maintenance.md` — adapter and ruleset lifecycle policies
