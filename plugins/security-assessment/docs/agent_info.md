# Agents

`security-assessment` ships thirteen **specialist agents** (all `opus` tier). They are invoked by the `/security-assessment` and `/cross-repo-analysis` orchestrators at specific pipeline phases — never directly by the user.

## Assessment agents

| Agent | File | Phase invoked | Purpose |
| --- | --- | --- | --- |
| `fp-reduction` | [`agents/fp-reduction.md`](../docs/agents/fp-reduction.md) | Phase 2 | 6-stage false-positive rubric (Stage 0 devil's-advocate + Stages 1–5); emits the disposition register with confidence scores |
| `business-logic-domain-review` | [`agents/business-logic-domain-review.md`](../docs/agents/business-logic-domain-review.md) | Phase 1b | Fraud-domain anti-pattern detection — enumeration abuse, account-takeover shapes, synthetic-identity signals |
| `deep-code-reasoning` | [`agents/deep-code-reasoning.md`](../docs/agents/deep-code-reasoning.md) | Phase 1b | RECON surface-scoped freeform vulnerability reasoning; surfaces novel context-dependent issues beyond static rules |
| `authorization-logic-review` | [`agents/authorization-logic-review.md`](../docs/agents/authorization-logic-review.md) | Phase 1b | Top-down authorization architecture review; policy declaration vs. enforcement gaps, multi-tenancy isolation |
| `recon-driven-scan` | [`agents/recon-driven-scan.md`](../docs/agents/recon-driven-scan.md) | Phase 1b | Bridges RECON narrative claims to concrete `file:line` evidence; finds patterns SAST cannot express (inverted-boolean TLS defaults, RCE via expression libraries, header-driven SQL, body-trusted IDOR) |
| `tool-finding-narrative-annotator` | Phase 3 | Phase 3 | 4-domain narrative synthesis (infrastructure, application, secrets, dependencies) |
| `compliance-edge-annotator` | Phase 3 | Phase 3 | LLM edge judgment for ambiguous compliance-mapping rows |
| `exec-report-generator` | [`agents/exec-report-generator.md`](../docs/agents/exec-report-generator.md) | Phase 5 | Publication-ready 7-section executive report with Confidence column |

## Cross-repo agents

| Agent | File | Purpose |
| --- | --- | --- |
| `cross-repo-synthesizer` | [`agents/cross-repo-synthesizer.md`](../docs/agents/cross-repo-synthesizer.md) | Named attack chains across multiple repos; produces Mermaid diagram + SARIF |

## Red-team agents

| Agent | File | Probe |
| --- | --- | --- |
| `redteam-recon-analyzer` | Phase C | Probe 01 — discovery |
| `redteam-evasion-analyzer` | Phase C | Probes 03 / 04 / 05 — input + output evasion |
| `redteam-extraction-analyzer` | Phase C | Probe 07 — data extraction |
| `redteam-report-generator` | Phase C | Final red-team report synthesis |

## Dispatch model

All agents in this plugin are `model: opus`. Model resolution follows the same Pre-dispatch Model Resolution procedure as the `dev-team` plugin (see [ADR-0004](../../docs/adr/0004-pre-dispatch-model-resolution.md)). The `agent_model_resolve.py` hook in `dev-team/hooks/` handles the alias → snapshot mapping; this plugin inherits that hook from the `dev-team` primitives contract.
