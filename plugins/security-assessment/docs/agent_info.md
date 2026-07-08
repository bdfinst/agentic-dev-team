# Agents

Agents in `security-assessment` are all **judgment agents** — they are never invoked directly by
the user, but are dispatched by the plugin's orchestrating commands during assessment phases.

## Judgment Agents

| Agent | File | Purpose | Invocation |
| --- | --- | --- | --- |
| authorization-logic-review | [`authorization-logic-review.md`](../agents/authorization-logic-review.md) | Top-down authorization review. Maps the access-control model (RBAC/ABAC/ACL/tenancy), then verifies enforcement at every layer. | Dispatched by `/security-assessment` Phase 1b |
| business-logic-domain-review | [`business-logic-domain-review.md`](../agents/business-logic-domain-review.md) | Business-logic review for ML/fraud services. Detects fail-open, score manipulation, and other domain-specific anti-patterns. | Dispatched by `/security-assessment` Phase 1b |
| compliance-edge-annotator | [`compliance-edge-annotator.md`](../agents/compliance-edge-annotator.md) | Edge annotator for compliance findings whose pattern row has `llm_review_trigger=true`. Refines pattern-table citations; never invents new findings. | Dispatched by `compliance-mapping` skill |
| cross-repo-synthesizer | [`cross-repo-synthesizer.md`](../agents/cross-repo-synthesizer.md) | Synthesizes attack-chain narratives from multi-repo RECON + shared-cred matches + service-comm diagram. Produces named attack chains. | Dispatched by `/cross-repo-analysis` |
| deep-code-reasoning | [`deep-code-reasoning.md`](../agents/deep-code-reasoning.md) | Context-aware vulnerability detection beyond static patterns. RECON-scoped freeform reasoning about IDOR, confused deputy, TOCTOU, privilege escalation, and similar classes. | Dispatched by `/security-assessment` Phase 1b |
| exec-report-generator | [`exec-report-generator.md`](../agents/exec-report-generator.md) | Synthesizes the publication-ready executive report from upstream artifacts. Emits a 7-section per-repo report plus cross-repo summary for multi-target runs. | Dispatched by `/security-assessment` Phase 5 and `/cross-repo-analysis` |
| fp-reduction | [`fp-reduction.md`](../agents/fp-reduction.md) | Applies the 5-stage FP-reduction rubric to a unified-finding stream, producing a disposition register with confidence field. | Dispatched by `false-positive-reduction` skill (Phase 2) |
| recon-driven-scan | [`recon-driven-scan.md`](../agents/recon-driven-scan.md) | Bridges RECON narrative risk claims to file:line evidence. Emits findings only when the source actually exhibits the described pattern. | Dispatched by `/security-assessment` Phase 1b |
| redteam-evasion-analyzer | [`redteam-evasion-analyzer.md`](../agents/redteam-evasion-analyzer.md) | Interprets probe 05 (evasion) alongside probe 03 (sensitivity) and probe 04 (boundaries). Rates adversarial realism and explains evasion mechanisms. | Dispatched by `/redteam-model` Phase 4 (parallel with other analyzers) |
| redteam-extraction-analyzer | [`redteam-extraction-analyzer.md`](../agents/redteam-extraction-analyzer.md) | Interprets probe 07 (model extraction) alongside probe 03 (sensitivity). Translates R² into extraction fidelity and extracts decision-rule signatures. | Dispatched by `/redteam-model` Phase 4 (parallel with other analyzers) |
| redteam-recon-analyzer | [`redteam-recon-analyzer.md`](../agents/redteam-recon-analyzer.md) | Interprets probe 01 (API recon). Severity-rates info leaks, identifies the framework, and recommends a feature-discovery strategy for subsequent probes. | Dispatched by `/redteam-model` Phase 4 (parallel with other analyzers) |
| redteam-report-generator | [`redteam-report-generator.md`](../agents/redteam-report-generator.md) | Refines the red-team `adversarial-report.md` into an executive document. Assigns RED/AMBER/GREEN rating and produces remediation with effort estimates. | Dispatched by `/redteam-model` Phase 5 |
| tool-finding-narrative-annotator | [`tool-finding-narrative-annotator.md`](../agents/tool-finding-narrative-annotator.md) | Weaves findings into four narrative domains (PII flow, ML edge cases, messaging auth, crypto). Produces prose for the executive report. | Dispatched by `security-assessment-pipeline` Phase 2b |
