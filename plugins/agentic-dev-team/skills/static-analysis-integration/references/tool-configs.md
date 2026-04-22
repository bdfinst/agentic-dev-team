# Tool Configurations (SARIF-first)

Per-tool invocation commands, install hints, and adapter-specific notes. Organized by tier per the skill's `## Tool tiers` section.

## Tier 1 — required baseline (SARIF native)

### semgrep

```bash
semgrep scan \
  --sarif \
  --config auto \
  --quiet \
  <target-paths>
```

- **Install**: `pip install semgrep`
- **Install hint**: `semgrep — SAST. install: pip install semgrep`
- **Detection**: `command -v semgrep`
- **Capability tier**: SAST
- **Adapter**: none; consumed raw by the shared SARIF parser.

### gitleaks

```bash
gitleaks detect \
  --report-format sarif \
  --report-path - \
  --source <path>
```

- **Install**: `brew install gitleaks` (macOS) / `docker run --rm -v "$PWD:/path" zricethezav/gitleaks:latest detect ...`
- **Install hint**: `gitleaks — secrets detection. install: brew install gitleaks`
- **Detection**: `command -v gitleaks`
- **Capability tier**: secrets
- **Adapter**: none.

### trivy

```bash
# IaC scanning
trivy config \
  --format sarif \
  --output /dev/stdout \
  <path>

# Filesystem / supply-chain scanning
trivy fs \
  --format sarif \
  --output /dev/stdout \
  --scanners vuln,config,secret \
  <path>
```

- **Install**: `brew install trivy`
- **Install hint**: `trivy — IaC + supply-chain scanning. install: brew install trivy`
- **Detection**: `command -v trivy`
- **Capability tier**: IaC + supply-chain
- **Adapter**: none.

### hadolint

```bash
hadolint --format sarif <Dockerfile>
```

- **Install**: `brew install hadolint`
- **Install hint**: `hadolint — Dockerfile linting. install: brew install hadolint`
- **Detection**: `command -v hadolint`
- **Capability tier**: IaC (Dockerfile)
- **Adapter**: none.

### actionlint

actionlint does not emit SARIF directly as of its current stable release.
Invoke with JSON output and wrap with a thin adapter (≤ 15 LOC) that
produces SARIF-compliant results.

```bash
actionlint -format '{{json .}}' <target-path>
```

The adapter maps each actionlint finding:

| actionlint field | SARIF field |
|---|---|
| `.Filepath` | `results[*].locations[0].physicalLocation.artifactLocation.uri` |
| `.Line` | `results[*].locations[0].physicalLocation.region.startLine` |
| `.Column` | `results[*].locations[0].physicalLocation.region.startColumn` |
| `.Kind` | `results[*].ruleId` |
| `.Message` | `results[*].message.text` |

Severity: all actionlint findings map to `warning` by default; upgrade to
`error` if `.Kind` starts with `shellcheck` and message contains "error".

- **Install**: `brew install actionlint`
- **Install hint**: `actionlint — GitHub Actions linting. install: brew install actionlint`
- **Detection**: `command -v actionlint`
- **Capability tier**: CI-CD
- **Adapter**: thin JSON → SARIF wrapper (see `adapters/actionlint-to-sarif.sh` — created in P2 Step 3b alongside the optional adapters).

## Tier 2 — optional SARIF adapters (shipped in P2 Step 3b)

Placeholder — populated by Step 3b. Expected tools: checkov, kube-linter, bandit, gosec, bearer, osv-scanner, grype, trufflehog.

## Tier 3 — bespoke JSON adapters (shipped in P2 Step 3b)

Placeholder — populated by Step 3b. Expected tools: detect-secrets, depcheck, deptry, kube-score, govulncheck. Each adapter is ≤ 40 LOC.

## Tier 4 — legacy (pre-SARIF)

### ESLint

```bash
npx eslint -f json <target-js-ts-files>
```

| ESLint JSON field | Unified finding field | Notes |
|---|---|---|
| `filePath` | `file` | |
| `messages[].line` | `line` | |
| `messages[].ruleId` | `rule_id` | Prefixed as `eslint.js.<rule-id>` |
| `messages[].message` | `message` | |
| `messages[].severity` (1=warn, 2=error) | `severity` | 1→`warning`, 2→`error` |

### TypeScript compiler

```bash
npx tsc --noEmit 2>&1
```

Output is line-based diagnostics; the legacy adapter parses
`<file>(line,col): error TSNNNN: <message>` entries and maps to
`rule_id: tsc.ts.ts<NNNN>`.

### pylint

```bash
pylint --output-format=json <target-py-files>
```

| pylint JSON field | Unified finding field |
|---|---|
| `path` | `file` |
| `line` | `line` |
| `column` | `column` |
| `symbol` | `rule_id` (prefixed `pylint.python.<symbol>`) |
| `message` | `message` |
| `type` | `severity` (`error`→`error`, `warning`/`convention`→`warning`, `refactor`/`info`→`suggestion`) |

Legacy adapters emit the same unified finding envelope as SARIF tools. Migrate to SARIF-native invocation when upstream support lands.
