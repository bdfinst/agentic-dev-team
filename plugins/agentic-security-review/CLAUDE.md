# agentic-security-review — Companion Plugin

Deep security assessment and adversarial ML red-team capability. Companion to `agentic-dev-team`, which provides the reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned security-primitives-contract, SARIF-first tool orchestration).

This plugin is **opinionated**: its hooks default ON, its red-team harness accepts only self-owned targets by default, and its orchestration enforces a fixed pipeline order. If you want primitives without the assessment machinery, install only `agentic-dev-team`.

## Structure Contract

This plugin mirrors `plugins/agentic-dev-team/` one-for-one; `harness/` is a first-class top-level directory for executable application code. The rule: "same schema where the directory applies; omitted directories documented here with rationale."

| Directory | Mirrors dev-team? | Rationale if omitted |
|---|---|---|
| `agents/` | yes | — |
| `skills/` | yes | — |
| `commands/` | yes | — |
| `hooks/` | yes | — |
| `knowledge/` | yes | — |
| `templates/` | yes | — |
| `prompts/` | yes | — |
| `harness/` | **new; not in dev-team** | Executable Python code for the red-team harness, service-comm parser, and custom tool scripts that need lifecycle beyond a shell wrapper |

## Hooks default ON (this plugin only)

The PostToolUse auto-scan hook fires on Edit/Write of matched file types. It is registered in THIS plugin's `settings.json` — NOT in `agentic-dev-team`. Default severity threshold: `error` only. Set `verbose_hooks: true` in `settings.local.json` to surface warnings too.

Opt-out: add this snippet to your `settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [] }
    ]
  }
}
```

(Removing the Stop hook in the same manner disables task-complete notifications.)

## SARIF-first tool orchestration

Findings flow through the shared SARIF parser in `plugins/agentic-dev-team/skills/static-analysis-integration` and normalize to the unified finding envelope v1.0 defined in `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`. This plugin ships three **custom semgrep rulesets** (`knowledge/semgrep-rules/{ml-patterns,llm-safety,fraud-domain}.yaml`) alongside invocations of the usual community rulesets (`p/security-audit`, `p/owasp-top-ten`, etc.).

## LLM-safety coverage bound (verbatim, required)

static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing

Runtime LLM-safety testing tools (`garak`, `rebuff`, `PyRIT`) are deferred to the red-team harness (Phase C). The static ruleset handles hardcoded LLM keys, insecure model loading (ONNX/pickle deserialization), and prompt-template string injection; it cannot cover adversarial inputs or emergent model behavior.

## Red-team target scope

`/redteam-model` accepts self-owned targets only by default:

- `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1` → accepted
- Public hostnames / IPs → refused unless `--self-certify-owned <path-to-authorization-artifact>` is provided. The artifact's SHA-256 is logged to the audit trail.

The refusal message includes a one-line example of `authorization.md` format. The full format reference ships at `knowledge/redteam-authorization.md`.

## Adapter Maintenance Policy

See `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md`. The companion plugin's custom adapters (e.g. actionlint's JSON→SARIF wrapper, the five bespoke-JSON adapters from Step 3b) follow the same policy: `maintainers:` list with minimum 2 names, tier-2 CI on installed binaries, 14-day escalation, three-release deprecation path.

## Ruleset Maintenance Policy

Each custom semgrep ruleset declares `maintainers:` (min 2) in its YAML frontmatter. Quarterly review cadence, 20% FP-drift threshold triggers triage, community PRs require positive + negative fixtures.

## Install

See `install.sh`. It performs four checks:

1. `agentic-dev-team` plugin present with compatible primitives contract version (`^1.0.0`).
2. Python ≥ 3.10 available (red-team harness requires it).
3. Tier-1 tool presence, grouped by capability tier. Required tools carry `[REQUIRED]` prefix; absence is a hard failure. Optional tools emit a warning.
4. Prints the exact `settings.local.json` opt-out snippet for anyone who wants hooks off.

## Dispatch registry

| Command | Role | Purpose |
|---|---|---|
| `/security-assessment <path>` | orchestrator | Full pipeline: recon → tool battery → LLM narrative agents → FP-reduction → compliance → service-comm diagram → exec report |
| `/cross-repo-analysis <paths>` | orchestrator | Shared credentials + service-comm analysis across multiple repos |
| `/redteam-model <target>` | orchestrator | Adversarial ML red-team probes against a self-owned target |
| `/export-pdf <report.md>` | worker | PDF export via pandoc/weasyprint |

**Agents** (9 opus):
- `fp-reduction` (opus) — 5-stage FP-reduction rubric; disposition register
- `business-logic-domain-review` (opus) — fraud-domain anti-patterns
- `cross-repo-synthesizer` (opus) — named attack chains across repos
- `exec-report-generator` (opus) — publication-ready executive report
- `redteam-recon-analyzer` (opus) — interpretation of probe 01
- `redteam-evasion-analyzer` (opus) — interpretation of probes 03/04/05
- `redteam-extraction-analyzer` (opus) — interpretation of probe 07
- `redteam-report-generator` (opus) — final red-team report synthesis
- `tool-finding-narrative-annotator` (opus) — 4-domain narrative synthesis
- `compliance-edge-annotator` (opus) — LLM edge judgment for ambiguous mappings

**Skills** (3):
- `false-positive-reduction` — 5-stage rubric + joern / LLM-fallback
- `compliance-mapping` — pattern-table first with LLM edge annotation
- `security-assessment-pipeline` — declarative phase graph for `/security-assessment`

**Commands** (4):
- `/security-assessment <path>` — full static-analysis pipeline
- `/cross-repo-analysis <paths>` — cross-repo attack-chain analysis
- `/redteam-model <target>` — adversarial ML red-team
- `/export-pdf <report.md>` — PDF export

**Hooks** (2):
- `PreToolUse:Bash` → `redteam-guard.sh` (blocks direct orchestrator invocation)
- `PostToolUse:Edit|Write` → `static-scan-on-edit.sh` (auto-scan on writes)

**Knowledge** (4):
- `domain-logic-patterns.md` — fraud domain anti-pattern reference
- `compliance-patterns.yaml` — 11-pattern regulatory mapping table
- `redteam-authorization.md` — self-cert artifact format
- `semgrep-rules/{ml-patterns,llm-safety,fraud-domain,crypto-anti-patterns}.yaml` — 18 custom rules across 4 rulesets

**Harness** (Python, under `harness/`):
- `redteam/orchestrator.py` + `config.py` + `lib/{http_client,result_store,scoring,feature_dict,scope_check}.py`
- 8 probes: `redteam/probes/{01..08}_*.py`
- `tools/{service-comm-parser,shared-cred-hash-match}.py`

See `plans/security-review-companion-plugin.md` for the step-by-step history.

## Not in this plugin

- The primitives contract itself (`security-primitives-contract.md`) — lives in `agentic-dev-team/knowledge/`
- The codebase-recon agent — lives in `agentic-dev-team/agents/`
- ACCEPTED-RISKS schema — lives in `agentic-dev-team/knowledge/`
- Baseline static-analysis orchestration — lives in `agentic-dev-team/skills/static-analysis-integration/`
- Static-scan hooks for general dev workflows (the PostToolUse auto-scan hook in THIS plugin is narrowly scoped to security-relevant file writes)
