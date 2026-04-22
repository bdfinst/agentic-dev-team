# agentic-security-review

Deep security assessment + adversarial ML red-team for Claude Code. Companion to [`agentic-dev-team`](../agentic-dev-team/), which provides the reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned primitives contract, SARIF-first tool orchestration).

## Design

Inverts the usual "LLM does everything" pattern: **deterministic tools do the detection**, hooks automate invocation, and LLM agents are reserved for what they do best — business-logic reasoning, narrative annotation, cross-repo attack chains, executive prose, and the judgment stages of FP-reduction.

## LLM-safety coverage bound

static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing

Static coverage handles hardcoded LLM keys, insecure model loading (ONNX/pickle deserialization), and prompt-template string injection. Runtime LLM-safety tools (`garak`, `rebuff`, `PyRIT`) are integrated via the red-team harness (Phase C) when needed.

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated.
- The [`agentic-dev-team`](../agentic-dev-team/README.md) plugin — this plugin depends on its primitives contract (`^1.0.0`), codebase-recon agent, and ACCEPTED-RISKS convention.
- Python ≥ 3.10 — required by the red-team harness.
- `jq` — JSON parsing in hooks + pipeline glue.

**Tier-1 static-analysis tools (required for `/security-assessment` to produce useful output):**

| Tool | Coverage | Install |
| --- | --- | --- |
| `semgrep` | SAST across every scan concern | `pip install semgrep` |
| `gitleaks` | Secrets / credentials in committed files | `brew install gitleaks` |
| `trivy` | IaC config + vulnerability DB | `brew install trivy` |
| `hadolint` | Dockerfile linting | `brew install hadolint` |
| `actionlint` | GitHub Actions linting | `brew install actionlint` |

**Optional tools** (broader coverage; the pipeline degrades gracefully without them): `checkov`, `bandit`, `gosec`, `bearer`, `osv-scanner`, `grype`, `kube-linter`, `trufflehog`, `detect-secrets`, `deptry`, `kube-score`, `govulncheck`, `pandoc`, `weasyprint`.

### Install the tools

**macOS — one command:**

```bash
./plugins/agentic-security-review/install-macos.sh           # tier-1 only
./plugins/agentic-security-review/install-macos.sh --all     # tier-1 + optional + PDF deps
./plugins/agentic-security-review/install-macos.sh --dry-run # preview commands without running
```

**Windows — PowerShell (requires [Scoop](https://scoop.sh)):**

```powershell
# If needed, allow local scripts first (run once in an elevated session):
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

.\plugins\agentic-security-review\install-windows.ps1          # tier-1 only
.\plugins\agentic-security-review\install-windows.ps1 -All     # tier-1 + optional + PDF deps
.\plugins\agentic-security-review\install-windows.ps1 -DryRun  # preview commands without running
```

Re-runnable on all platforms — each step skips tools that are already present.

**Linux / other platforms:** use the install hints in the table above. All tools ship prebuilt Linux binaries via their GitHub releases or `pip`.

### Install the plugin

```bash
# From the marketplace
claude plugin marketplace add https://github.com/bdfinst/agentic-dev-team
claude plugin install agentic-security-review@bfinster

# From a local clone
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-security-review
```

### Verify

```bash
./plugins/agentic-security-review/install.sh
```

The check validates:

1. `agentic-dev-team` present with primitives-contract `^1.0.0`.
2. Python ≥ 3.10 on PATH.
3. Tier-1 tool presence. Absence of any required tool is a hard failure.
4. Optional tool presence — warnings only.

### Run without installing (zero-install flow)

`scripts/run-assessment-local.sh` runs the full pipeline from the repo checkout. Auto-detects the `claude` CLI and runs the LLM judgment phases when available; degrades to deterministic-only output otherwise. See [`docs/user-guide-security-assessment.md`](../../docs/user-guide-security-assessment.md) for the full runbook.

## Commands

| Command | Purpose |
|---|---|
| `/security-assessment <path>` | Full pipeline: recon → tool battery → LLM narrative agents → FP-reduction → compliance → service-comm diagram → exec report |
| `/cross-repo-analysis <paths>` | Shared credentials and service-communication analysis across multiple repos |
| `/redteam-model <target>` | Adversarial ML red-team probes against a self-owned target |
| `/export-pdf <report.md>` | PDF export via pandoc / weasyprint |

## Safety defaults

- **Hooks default ON** in this plugin (see `CLAUDE.md` § "Hooks default ON"). The PostToolUse auto-scan hook fires on Edit/Write of security-relevant file types.
- **Red-team targets default to self-owned only**: localhost + RFC1918 + `::1`. Public targets require an explicit `--self-certify-owned` artifact whose SHA-256 is logged to the audit trail.

See `CLAUDE.md` for the opt-out snippet.

## Status

Phase A primitives (in `agentic-dev-team`) are landing in parallel:

- ✅ codebase-recon agent
- ✅ ACCEPTED-RISKS convention
- ✅ security-primitives-contract v1.0.0
- ✅ contract-version-guard hook
- ✅ SARIF-first orchestration baseline (tier-1 adapters)
- ⏳ optional + bespoke-JSON adapters + custom scripts + rulesets (Step 3b)

Phase B / C / D work (this plugin's own agents, FP-reduction, red-team harness, exec report, release-please config) is scaffolded and in-progress. See `plans/security-review-companion-plugin.md`.
