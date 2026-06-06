# security-assessment

Deep security assessment + adversarial ML red-team for Claude Code. Companion to [`dev-team`](../dev-team/), which provides the reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned primitives contract, SARIF-first tool orchestration).

## Design

Inverts the usual "LLM does everything" pattern: **deterministic tools do the detection**, hooks automate invocation, and LLM agents are reserved for what they do best — business-logic reasoning, narrative annotation, cross-repo attack chains, executive prose, and the judgment stages of FP-reduction.

## When to use this vs. `/code-review`

This plugin is the **deep layer**. Use it for audits, release gates, milestone reviews, publication-grade reports, and red-team runs. Runtime is minutes (recon → parallel tools → parallel judgment → FP-reduction → narratives → exec report).

For **inline checkpoints during active development**, use `/code-review`, which invokes the sibling `security-review` agent from the `dev-team` plugin. That's a single opus pass in seconds, appropriate for every commit. The agent is also what this plugin invokes internally at Phase 1b of `/security-assessment` — so running the agent during development is complementary, not redundant. When a `/code-review` finding warrants deeper analysis (FP-reduction, reachability, compliance mapping, domain-layer review), escalate to `/security-assessment` here.

Pattern-visible vulnerability classes (single-line regex, stable AST shape, ≤10% false-positive rate) are authoritatively detected by the semgrep rules under `knowledge/semgrep-rules/*.yaml` — not by agent prompts. The class → surface boundary is encoded in `plugins/dev-team/knowledge/security-review-rule-map.yaml`.

## LLM-safety coverage bound

static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing

Static coverage handles hardcoded LLM keys, insecure model loading (ONNX/pickle deserialization), and prompt-template string injection. Runtime LLM-safety tools (`garak`, `rebuff`, `PyRIT`) are integrated via the red-team harness (Phase C) when needed.

## Install

### Prerequisites

**Required:**

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated.
- The [`dev-team`](../dev-team/README.md) plugin — this plugin depends on its primitives contract (`^1.0.0`), codebase-recon agent, and ACCEPTED-RISKS convention.
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
./plugins/security-assessment/install-macos.sh           # tier-1 only
./plugins/security-assessment/install-macos.sh --all     # tier-1 + optional + PDF deps
./plugins/security-assessment/install-macos.sh --dry-run # preview commands without running
```

**Windows — PowerShell (requires [Scoop](https://scoop.sh)):**

```powershell
# If needed, allow local scripts first (run once in an elevated session):
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

.\plugins\security-assessment\install-windows.ps1          # tier-1 only
.\plugins\security-assessment\install-windows.ps1 -All     # tier-1 + optional + PDF deps
.\plugins\security-assessment\install-windows.ps1 -DryRun  # preview commands without running
```

Re-runnable on all platforms — each step skips tools that are already present.

**Linux / other platforms:** use the install hints in the table above. All tools ship prebuilt Linux binaries via their GitHub releases or `pip`.

### Install the plugin

```bash
# From the marketplace
claude plugin marketplace add https://github.com/bdfinst/dev-team
claude plugin install security-assessment@bfinster

# From a local clone
claude plugin install --scope project /path/to/dev-team/plugins/security-assessment
```

### Verify

```bash
./plugins/security-assessment/install.sh
```

The check validates:

1. `dev-team` present with primitives-contract `^1.0.0`.
2. Python ≥ 3.10 on PATH.
3. Tier-1 tool presence. Absence of any required tool is a hard failure.
4. Optional tool presence — warnings only.

### Run without installing (zero-install flow)

`scripts/run-assessment-local.sh` runs the full pipeline from the repo checkout. Auto-detects the `claude` CLI and runs the LLM judgment phases when available; degrades to deterministic-only output otherwise. See [`docs/user-guide-security-assessment.md`](docs/user-guide-security-assessment.md) for the full runbook.

## Commands

| Command | Purpose |
|---|---|
| `/security-assessment <path>` | Full pipeline: recon → tool battery → LLM narrative agents → FP-reduction → compliance → service-comm diagram → exec report |
| `/cross-repo-analysis <paths>` | Shared credentials and service-communication analysis across multiple repos |
| `/redteam-model <target>` | Adversarial ML red-team probes against a self-owned target |
| `/export-pdf <report.md>` | PDF export via pandoc / weasyprint |
| `/upgrade` | Update the plugin to the latest marketplace release; offer to enable marketplace-level auto-update |

## Update

Run `/upgrade` from any Claude Code session with this plugin loaded. It:

1. Reads the installed version from `claude plugin list`.
2. Checks the auto-update flag on the `bfinster` marketplace and asks for consent before enabling it (the same flag the `/plugin` UI toggles).
3. Detects the install scope and passes `--scope <scope>` to `claude plugin update` so project- and local-scope installs upgrade correctly.
4. Warns if the companion `dev-team` plugin is not installed (it provides primitives this plugin depends on).
5. Reports the previous and new version, and prompts a restart.

Migration from the pre-rename `agentic-security-assessment@bfinster` id is handled by the legacy deprecation stub published in the marketplace catalog — install or `/upgrade` from that stub and it will install `security-assessment@bfinster` then remove itself.

Manual fallback when `/upgrade` is unavailable:

```bash
claude plugin update --scope <scope> security-assessment@bfinster
```

## Safety defaults

- **Hooks default ON** in this plugin (see `CLAUDE.md` § "Hooks default ON"). The PostToolUse auto-scan hook fires on Edit/Write of security-relevant file types.
- **Red-team targets default to self-owned only**: localhost + RFC1918 + `::1`. Public targets require an explicit `--self-certify-owned` artifact whose SHA-256 is logged to the audit trail.

See `CLAUDE.md` for the opt-out snippet.

## Status

Phase A primitives (in `dev-team`) are landing in parallel:

- ✅ codebase-recon agent
- ✅ ACCEPTED-RISKS convention
- ✅ security-primitives-contract v1.0.0
- ✅ contract-version-guard hook
- ✅ SARIF-first orchestration baseline (tier-1 adapters)
- ⏳ optional + bespoke-JSON adapters + custom scripts + rulesets (Step 3b)

Phase B / C / D work (this plugin's own agents, FP-reduction, red-team harness, exec report, release-please config) is scaffolded and in-progress. See `plans/security-review-companion-plugin.md`.
