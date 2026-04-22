# agentic-security-review

Deep security assessment + adversarial ML red-team for Claude Code. Companion to [`agentic-dev-team`](../agentic-dev-team/), which provides the reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned primitives contract, SARIF-first tool orchestration).

## Design

Inverts the usual "LLM does everything" pattern: **deterministic tools do the detection**, hooks automate invocation, and LLM agents are reserved for what they do best — business-logic reasoning, narrative annotation, cross-repo attack chains, executive prose, and the judgment stages of FP-reduction.

## LLM-safety coverage bound

static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing

Static coverage handles hardcoded LLM keys, insecure model loading (ONNX/pickle deserialization), and prompt-template string injection. Runtime LLM-safety tools (`garak`, `rebuff`, `PyRIT`) are integrated via the red-team harness (Phase C) when needed.

## Install

```bash
# From the marketplace
claude plugin install agentic-security-review@bfinster

# From local checkout
claude plugin install --scope project /path/to/agentic-dev-team/plugins/agentic-security-review

# Verify prerequisites
./plugins/agentic-security-review/install.sh
```

The install check validates:
1. `agentic-dev-team` is installed with a compatible primitives-contract version (^1.0.0).
2. Python ≥ 3.10 for the red-team harness.
3. Tier-1 static-analysis tools (semgrep, gitleaks, trivy, hadolint, actionlint). Absence of any required tool is a hard failure.
4. Optional Tier 2 / Tier 3 tools. Absence emits warnings only.

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
