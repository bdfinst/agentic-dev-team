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
  --no-verify \
  --source <path>
```

- **Install**: `brew install gitleaks` (macOS) / `docker run --rm -v "$PWD:/path" zricethezav/gitleaks:latest detect ...`
- **Install hint**: `gitleaks — secrets detection. install: brew install gitleaks`
- **Detection**: `command -v gitleaks`
- **Capability tier**: secrets
- **Offline posture**: `--no-verify` disables gitleaks' active-credential verification, which would otherwise make outbound API calls (e.g. to AWS/GitHub) to confirm a detected secret is live. Detection is purely pattern-based and runs with zero network egress. Always on — this flag carries no detection cost.
- **Adapter**: none.

### trivy

```bash
# IaC scanning
trivy config \
  --format sarif \
  --output /dev/stdout \
  --skip-update \
  --offline-scan \
  <path>

# Filesystem / supply-chain scanning
trivy fs \
  --format sarif \
  --output /dev/stdout \
  --scanners vuln,config,secret \
  --skip-update \
  --offline-scan \
  <path>
```

- **Install**: `brew install trivy`
- **Install hint**: `trivy — IaC + supply-chain scanning. install: brew install trivy`
- **Detection**: `command -v trivy`
- **Capability tier**: IaC + supply-chain
- **Offline posture**: both `trivy config` and `trivy fs` run with `--skip-update --offline-scan`. `--skip-update` pins trivy to the local vulnerability DB (no DB refresh over the network); `--offline-scan` suppresses the remote metadata lookups trivy otherwise performs for some package ecosystems. Run the **offline DB preflight** below before dispatch.
- **Offline DB preflight**: locate the local DB at trivy's cache path (`${TRIVY_CACHE_DIR:-$HOME/.cache/trivy}/db/trivy.db`) and check its `mtime`:
  - **absent** → skip trivy, warn `trivy local DB missing — run: trivy image --download-db-only`
  - **mtime age ≤ 7 days** → run normally (fresh)
  - **mtime age > 7 days** → run anyway, warn `trivy DB is N days old — consider refreshing with: trivy image --download-db-only` (substitute `N` with the integer day count)

  The 7-day boundary is inclusive: exactly 7 days old is still fresh; strictly greater than 7 days is stale. A missing or stale DB is never a hard pipeline failure.
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

## Build-time lanes

The registry for `/build`'s static self-heal pass: one subsection per
language lane, filled in by the issue that registers the lane with the lane's
file extensions, each capability slot's (**autofix** / **diagnostic**)
ordered provider list — default provider first; it doubles as the last-resort
provider named by install hints — and each provider's detection probe
(repo-local locations first, then PATH).

Everything else — what a lane is, scoping, the shared fix loop, the
2-attempt cap, detection/provider binding, the provider qualification
contract, the degradation ladder, granularity, and ordering — is specified
once, in `${CLAUDE_PLUGIN_ROOT}/skills/build/references/static-self-heal.md`.
Rows registered here must satisfy that contract and must not restate the
mechanism. User-facing setup for each lane lives in
[`language-setup.md`](language-setup.md).

A language whose subsection still reads "No lane registered" is skipped by
the self-heal pass with one info line — never a failure.

### Python lane

No lane registered — placeholder. Registered by #807.

### JS/TS lane

No lane registered — placeholder. Registered by #808.

### C# lane

No lane registered — placeholder. Registered by #809.

### Java lane

No lane registered — placeholder. Registered by #810.
