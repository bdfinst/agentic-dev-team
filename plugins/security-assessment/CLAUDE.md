# security-assessment — Companion Plugin

Deep security assessment and adversarial ML red-team capability. Companion to `dev-team`, which provides the reusable primitives (codebase-recon, ACCEPTED-RISKS convention, versioned security-primitives-contract, SARIF-first tool orchestration).

This plugin is **opinionated**: hooks default ON, the red-team harness accepts only self-owned targets by default, and orchestration enforces a fixed pipeline order. Want primitives without the assessment machinery? Install only `dev-team`.

## Structure Contract

Mirrors `plugins/dev-team/` one-for-one, plus `harness/` — a top-level dir for executable application code.

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

The PostToolUse auto-scan hook fires on Edit/Write of matched file types. Registered in THIS plugin's `settings.json`, not `dev-team`'s. Default severity threshold: `error` only; set `verbose_hooks: true` in `settings.local.json` to surface warnings too.

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

Findings flow through the shared SARIF parser in `plugins/dev-team/skills/static-analysis-integration` and normalize to the unified finding envelope v1.0 in `plugins/dev-team/knowledge/security-primitives-contract.md`. Ships seven **custom semgrep rulesets** (`knowledge/semgrep-rules/{crypto-anti-patterns,datastore-patterns,fraud-domain,llm-safety,messaging-patterns,ml-patterns,serialization-patterns}.yaml`) alongside the usual community rulesets (`p/security-audit`, `p/owasp-top-ten`, etc.).

## LLM-safety coverage bound (verbatim, required)

static coverage via llm-safety.yaml is intentionally narrow — it catches pattern-visible issues but is NOT a substitute for runtime LLM safety testing

Runtime LLM-safety tools (`garak`, `rebuff`, `PyRIT`) are deferred to the red-team harness (Phase C). The static ruleset handles hardcoded LLM keys, insecure model loading (ONNX/pickle deserialization), and prompt-template string injection — not adversarial inputs or emergent model behavior.

## Red-team target scope

`/redteam-model` accepts self-owned targets only by default:

- `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1` → accepted
- Public hostnames / IPs → refused unless `--self-certify-owned <path-to-authorization-artifact>` is provided. The artifact's SHA-256 is logged to the audit trail.

The refusal message includes a one-line example of `authorization.md` format. The full format reference ships at `knowledge/redteam-authorization.md`.

## Adapter Maintenance Policy

Custom adapters (actionlint's JSON→SARIF wrapper, the 5 bespoke-JSON adapters) follow `static-analysis-integration/SKILL.md`'s policy: `maintainers:` (min 2), tier-2 CI, 14-day escalation, 3-release deprecation.

## Ruleset Maintenance Policy

Each custom semgrep ruleset declares `maintainers:` (min 2) in its YAML frontmatter. Quarterly review cadence, 20% FP-drift threshold triggers triage, community PRs require positive + negative fixtures.

## Install

See `install.sh`. It performs four checks:

1. `dev-team` plugin present with compatible primitives contract version (`^1.0.0`).
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
| `/upgrade` | worker | Update the security-assessment plugin and optionally enable marketplace auto-update |

**Agents** (13, effort: high):

- `fp-reduction` — 6-stage FP-reduction rubric (Stage 0 devil's advocate + Stages 1–5); disposition register with confidence field
- `business-logic-domain-review` — fraud-domain anti-patterns
- `deep-code-reasoning` — RECON surface-scoped freeform vulnerability reasoning; novel context-dependent issues beyond static rules
- `authorization-logic-review` — top-down authorization architecture review; policy declaration vs. enforcement gaps, multi-tenancy isolation
- `recon-driven-scan` — bridges RECON narrative claims to concrete file:line evidence; finds patterns SAST cannot express (inverted-boolean TLS defaults, RCE shapes via expression libraries, header-driven SQL, body-trusted IDOR)
- `cross-repo-synthesizer` — named attack chains across repos
- `exec-report-generator` — publication-ready executive report with Confidence column
- `redteam-recon-analyzer` — interpretation of probe 01
- `redteam-evasion-analyzer` — interpretation of probes 03/04/05
- `redteam-extraction-analyzer` — interpretation of probe 07
- `redteam-report-generator` — final red-team report synthesis
- `tool-finding-narrative-annotator` — 4-domain narrative synthesis
- `compliance-edge-annotator` — LLM edge judgment for ambiguous mappings

**Skills** (3):

- `false-positive-reduction` — 6-stage rubric (Stage 0 devil's advocate + Stages 1–5) + joern / LLM-fallback
- `compliance-mapping` — pattern-table first with LLM edge annotation
- `security-assessment-pipeline` — declarative phase graph for `/security-assessment`

**Commands** (5):

- `/security-assessment <path>` — full static-analysis pipeline
- `/cross-repo-analysis <paths>` — cross-repo attack-chain analysis
- `/redteam-model <target>` — adversarial ML red-team
- `/export-pdf <report.md>` — PDF export
- `/upgrade` — plugin update + auto-update opt-in

**Hooks** (3):

- `PreToolUse:Bash` → `redteam-guard.sh` (blocks direct orchestrator invocation)
- `PostToolUse:Edit|Write` → `static-scan-on-edit.sh` (auto-scan on writes)
- `PreToolUse:Agent` + `PostToolUse:Agent` → `agent-dispatch-log.sh` (times every agent dispatch to `memory/agent-dispatches.jsonl`)

**Knowledge** (9):

- `domain-logic-patterns.md` — fraud domain anti-pattern reference
- `compliance-patterns.yaml` — 11-pattern regulatory mapping table
- `redteam-authorization.md` — self-cert artifact format
- `severity-floors.json` — allow-listed floor classes for `scripts/apply-severity-floors.sh`
- `disclaimers.md` — verbatim-wording disclaimers cited by agents and skills
- `exec-report-section6-spec.md` — detailed spec for the exec report's Methodology/Scope section
- `recon-driven-patterns.yaml` — RECON claim → search-pattern library for `recon-driven-scan`
- `authz-review-categories.yaml` — rule-ID categories and CWE assignments for `authorization-logic-review`
- `phase-1b-adapters.md` — Phase 1b finding-stream append paths per agent output shape
- `semgrep-rules/{crypto-anti-patterns,datastore-patterns,fraud-domain,llm-safety,messaging-patterns,ml-patterns,serialization-patterns}.yaml` — 36 custom rules across 7 rulesets

**Harness** (Python, under `harness/`):

- `redteam/orchestrator.py` + `config.py` + `lib/{http_client,result_store,scoring,feature_dict,scope_check}.py`
- 8 probes: `redteam/probes/probe_{01..08}_*.py`
- `tools/{service-comm-parser,shared-cred-hash-match}.py`

## Not in this plugin

- The primitives contract itself (`security-primitives-contract.md`) — lives in `dev-team/knowledge/`
- The codebase-recon agent — lives in `dev-team/agents/`
- ACCEPTED-RISKS schema registry — Envelope 4 of `plugins/dev-team/knowledge/security-primitives-contract.md`; input format reference at `plugins/security-assessment/docs/accepted-risks-format.md`
- Baseline static-analysis orchestration — lives in `dev-team/skills/static-analysis-integration/`
- Static-scan hooks for general dev workflows (the PostToolUse auto-scan hook in THIS plugin is narrowly scoped to security-relevant file writes)
