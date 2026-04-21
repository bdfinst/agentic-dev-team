---
name: security-primitives-contract
description: Versioned cross-plugin contract defining the data envelopes passed between agentic-dev-team and agentic-security-review. Agent IDs, skill IDs, and three JSON schemas (RECON, unified finding, disposition register). Consumers declare `required-primitives-contract: ^1.0.0`.
version: 1.0.0
semver-policy: |
  PATCH (1.0.x) — clarifications, typo fixes, documentation improvements; no
                  schema changes.
  MINOR (1.x.0) — additive schema changes (new OPTIONAL fields, new enum
                  values, new agent IDs, new skill IDs). Consumers on
                  prior 1.x.0 continue to work; new features ignored.
  MAJOR (x.0.0) — breaking changes (renamed or removed fields, changed
                  semantics, new REQUIRED fields, removed enum values).
                  Consumers on prior major MUST be updated.
---

# Security Primitives Contract v1.0.0

This file is the single source of truth for the data envelopes exchanged between `plugins/agentic-dev-team/` (producer of primitives) and `plugins/agentic-security-review/` (consumer). Downstream plugins declare compatibility via `required-primitives-contract: ^1.0.0` in their `plugin.json`.

The contract covers three data envelopes and two registries. Per-tool raw outputs are **explicitly not in the contract** — they are normalized into the unified finding envelope by SARIF-first adapters in `skills/static-analysis-integration/SKILL.md`. That normalization layer is an implementation detail behind the contract, free to evolve under PATCH releases.

## Bypass path

Edits to this file are guarded by `hooks/contract-version-guard.sh`. A body change without a `version` field bump is blocked. Bypass is auto-granted only for release-please commits (matched by author `release-please[bot]` or commit-message prefix `chore(main): release`).

## Registries

### Agent IDs (1.0.0)

Agents that produce or consume contract envelopes. Each ID is stable across the major version. Renames trigger a MAJOR bump.

| Agent ID | Produces | Consumes | Defined in |
|---|---|---|---|
| `codebase-recon` | RECON envelope | — | `plugins/agentic-dev-team/agents/codebase-recon.md` |
| `security-review` | unified findings | — | `plugins/agentic-dev-team/agents/security-review.md` |
| `fp-reduction` | disposition register | unified findings, RECON | `plugins/agentic-security-review/agents/fp-reduction.md` (companion plugin) |
| `tool-finding-narrative-annotator` | — | unified findings, RECON | `plugins/agentic-security-review/agents/tool-finding-narrative-annotator.md` (companion plugin) |
| `business-logic-domain-review` | unified findings (domain-level) | — | `plugins/agentic-security-review/agents/business-logic-domain-review.md` (companion plugin) |
| `cross-repo-synthesizer` | — | RECON, unified findings | `plugins/agentic-security-review/agents/cross-repo-synthesizer.md` (companion plugin) |
| `exec-report-generator` | — | all three envelopes | `plugins/agentic-security-review/agents/exec-report-generator.md` (companion plugin) |

Adding an agent ID is a MINOR bump. Removing one is a MAJOR bump.

### Skill IDs (1.0.0)

Skills that participate in the contract (operate on envelopes or define adapter behavior).

| Skill ID | Role | Defined in |
|---|---|---|
| `static-analysis-integration` | SARIF-first adapters; produces unified findings from per-tool outputs | `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md` |
| `false-positive-reduction` | Consumes unified findings, produces disposition register | `plugins/agentic-security-review/skills/false-positive-reduction/SKILL.md` (companion plugin) |
| `compliance-mapping` | Consumes unified findings, emits compliance annotations (not in contract — downstream-only) | `plugins/agentic-security-review/skills/compliance-mapping/SKILL.md` (companion plugin) |
| `security-assessment-pipeline` | Orchestrates full envelope flow end-to-end | `plugins/agentic-security-review/skills/security-assessment-pipeline/SKILL.md` (companion plugin) |

## Envelope 1 — RECON

Normalized reconnaissance output from `codebase-recon`. Schema: `knowledge/schemas/recon-envelope-v1.json`.

Key design notes:
- Superset of the `codebase-recon` v0.1 placeholder; `schema_version` bumps to `"1.0"`.
- Added under 1.0: `repo.vcs` object (distinguishes git from non-git repos), `architecture.notable_anti_patterns` (open-ended notes from the recon pass), `security_surface.csp_headers` (referenced in security contexts).
- All v0.1 field names remain stable.

## Envelope 2 — Unified finding

Narrow normalization over SARIF `result` objects. Schema: `knowledge/schemas/unified-finding-v1.json`.

Required fields only. Per-tool raw output is NOT part of the contract (it is accessible via the `metadata.source_ref` field for debugging but consumers must not depend on its shape).

Required fields:
- `rule_id` — string, format `<source>.<language?>.<rule>` (e.g. `semgrep.python.hardcoded-password`, `gitleaks.generic.aws-access-key`)
- `file` — repo-relative path
- `line` — 1-indexed integer
- `severity` — enum: `error | warning | suggestion | info`
- `message` — one-line human-readable summary
- `metadata` — object with `source` (string: tool name), `confidence` (enum: `high | medium | low | none`)

Optional:
- `column` — 1-indexed integer
- `end_line`, `end_column`
- `cwe`, `cve`, `owasp` — string arrays
- `metadata.source_ref` — opaque pointer to the raw tool output (debugging aid only; not stable)
- `metadata.exploitability` — enum: `demonstrated | plausible | theoretical | unknown`

## Envelope 3 — Disposition register

Output of `fp-reduction` over unified findings. Schema: `knowledge/schemas/disposition-register-v1.json`.

One disposition entry per unified finding processed. Each entry:
- `finding` — the unified finding being dispositioned (embedded verbatim, not a reference)
- `verdict` — enum: `true_positive | likely_true_positive | uncertain | likely_false_positive | false_positive`
- `reachability` — object: `{ reachable: bool, rationale: string }`
- `reachability_source` — enum: `joern-cpg | llm-fallback` (drives exec report's fallback banner per P2 Phase B)
- `exploitability` — object: `{ score: 0-10, rationale: string }`
- `dispositioner` — string: agent ID that produced this disposition (typically `fp-reduction`)
- `dispositioned_at` — ISO-8601 timestamp

## Out of contract

Explicitly NOT part of this contract:

- Per-tool raw outputs (SARIF documents, JSON outputs from bespoke adapters). These flow through the adapter layer and are normalized into unified findings. Consumers treat adapters as opaque — the unified finding envelope is the contract boundary.
- Internal adapter configuration (`references/tool-configs.md` layouts, matcher regexes). These are implementation details of `skills/static-analysis-integration`.
- Compliance mapping outputs. These are a downstream product of the companion plugin, not shared cross-plugin primitives.
- Report templates (executive report sections, Mermaid diagrams). These are presentation concerns.
- Red-team harness artifacts. The harness ships its own schemas under `plugins/agentic-security-review/harness/redteam/schemas/` — separate lifecycle, separate versioning.

## Conformance

Schemas live at `plugins/agentic-dev-team/knowledge/schemas/{recon-envelope,unified-finding,disposition-register}-v1.json` and must validate using any Draft 2020-12 JSON Schema validator.

Conformance fixtures at `evals/primitives-contract/fixtures/` exercise each envelope against positive and negative cases. The `/agent-audit` command validates references to this file (agent IDs cited elsewhere in the plugin must match the registry above).

A mutation test alters a field in a conformance fixture; CI must fail. A version-mismatch mock (producer 2.0.0 vs. consumer `^1.0.0`) exercises the `install.sh` refusal path.

## Versioning lifecycle

- Clarifications and typos → open a PR with `version: 1.0.X` (PATCH).
- New optional fields, new enum values, new agent or skill IDs → `version: 1.X.0` (MINOR). Update the relevant schema file; add a fixture; document the addition under `## Changelog`.
- Removing a field, renaming a field, changing a field's semantics, or adding a REQUIRED field → `version: X.0.0` (MAJOR). Publish a migration note; downstream plugins' `required-primitives-contract` constraints force them to update before installing.

## Changelog

### 1.0.0 (2026-04-21)

Initial contract. Finalizes the RECON envelope v0.1 placeholder from `codebase-recon`. Defines unified finding envelope as a narrow SARIF `result` normalization. Defines disposition register as the FP-reduction output envelope. Registers initial agent and skill IDs.
