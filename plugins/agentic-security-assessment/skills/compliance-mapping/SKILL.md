---
name: compliance-mapping
description: Pattern-table-first mapping from unified findings to regulatory control citations (PCI-DSS, GDPR, HIPAA, SOC2). Deterministic table lookup first; LLM edge-case annotator invoked ONLY for findings whose pattern has llm_review_trigger=true. Report carries informational disclaimer.
role: worker
user-invocable: false
version: 1.0.0
maintainers:
  - bdfinst
  - unassigned
required-primitives-contract: ^1.0.0
---

# Compliance Mapping (pattern-first)

## Purpose

Map unified findings to regulatory control citations so executive-audience reports can name the specific regulations at risk. Designed to be deterministic first — a pattern table handles the bulk; LLM judgment is invoked ONLY for cases the table flags as ambiguous.

This is explicitly **informational, not audit-grade**. No report produced by this pipeline substitutes for a certified auditor's opinion. The disclaimer is mandatory and exact-wording.

## Inputs

- Disposition register (post-fp-reduction unified findings with verdicts)
- `knowledge/compliance-patterns.yaml` (this plugin) — the pattern table
- Optional: target organization's pre-declared control scope (which regulations apply)

## Output

A `compliance-annotations.json` file per the following shape:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-04-21T10:00:00Z",
  "disclaimer": "This compliance mapping is informational and derived from pattern matching. It does not constitute a certified audit and should not be used as a substitute for formal compliance review.",
  "annotations": [
    {
      "finding_rule_id": "semgrep.python.hardcoded-password",
      "finding_file": "config/prod.py",
      "finding_line": 42,
      "regulations": [
        {"regulation": "PCI-DSS", "control_id": "3.2.1", "citation": "PCI-DSS v4.0 §3.2.1"},
        {"regulation": "GDPR", "control_id": "Art. 32", "citation": "GDPR Article 32 — Security of Processing"}
      ],
      "annotator": "pattern-table"   // or "llm" if llm_review_trigger fired
    }
  ]
}
```

## Pattern table schema (`knowledge/compliance-patterns.yaml`)

Each row maps a finding pattern to one or more regulatory citations.

```yaml
# plugins/agentic-security-assessment/knowledge/compliance-patterns.yaml
patterns:
  - id: pan-at-log
    pattern_regex: 'log\.(debug|info).*(pan|card_number|primary_account)'
    field_type: "pii.pan"
    applies_to_rules:
      - "semgrep.*.pii-log"
      - "business-logic.fraud.tokenization-skip-under-flag"
    regulations:
      - regulation: "PCI-DSS"
        control_id: "3.4"
        citation: "PCI-DSS v4.0 §3.4 — PAN must be rendered unreadable in storage and in logs"
      - regulation: "PCI-DSS"
        control_id: "10.2"
        citation: "PCI-DSS v4.0 §10.2 — Audit logs must not contain sensitive authentication data"
    llm_review_trigger: false

  - id: unencrypted-db-transit
    pattern_regex: "(mongodb|postgres|mysql)://[^@]+@[^/]+/[^?]+($|(?!.*ssl|.*tls))"
    field_type: "db.transit"
    applies_to_rules:
      - "semgrep.*.unencrypted-database-connection"
      - "trivy.iac.*"
    regulations:
      - regulation: "PCI-DSS"
        control_id: "4.1"
        citation: "PCI-DSS v4.0 §4.1 — Strong cryptography and security protocols on open public networks"
      - regulation: "GDPR"
        control_id: "Art. 32"
        citation: "GDPR Article 32 — Security of Processing"
    llm_review_trigger: false

  - id: auth-bypass-admin
    pattern_regex: ".*admin.*"
    field_type: "auth.missing"
    applies_to_rules:
      - "semgrep.*.missing-csrf"
      - "semgrep.*.unauthenticated-endpoint"
      - "business-logic.fraud.*"
    regulations:
      - regulation: "PCI-DSS"
        control_id: "8.3"
        citation: "PCI-DSS v4.0 §8.3 — Multi-factor authentication for admin access"
      - regulation: "SOC2"
        control_id: "CC6.1"
        citation: "SOC2 Trust Services Criteria CC6.1 — Logical access controls"
    llm_review_trigger: true   # rules in this class often need case-specific judgment

  - id: insecure-random
    pattern_regex: ".*"
    field_type: "crypto.random"
    applies_to_rules:
      - "semgrep.*.insecure-random"
    regulations:
      - regulation: "PCI-DSS"
        control_id: "3.6.1"
        citation: "PCI-DSS v4.0 §3.6.1 — Cryptographic key generation practices"
    llm_review_trigger: false
```

Schema fields per row:

| Field | Required | Type | Purpose |
|---|---|---|---|
| `id` | yes | string | Stable identifier |
| `pattern_regex` | yes | string | Regex applied to the finding's message / file / context |
| `field_type` | yes | string | Categorical tag (pii.pan, auth.missing, crypto.random, etc.) for audit traceability |
| `applies_to_rules` | yes | list[string] | Rule-id glob patterns this row matches |
| `regulations` | yes | list[object] | One or more citation objects |
| `llm_review_trigger` | no | bool (default false) | If true, LLM edge annotator is invoked for findings matched by this row |

## Procedure

### 1. Load and validate the pattern table

Parse YAML. Every row MUST have the required fields. An invalid row fails the run with a named error pointing to the row `id`.

### 2. For each finding in the disposition register

Apply rows in file-declaration order:

1. Check `applies_to_rules` globs against `finding.rule_id`. No match → skip row.
2. Check `pattern_regex` against `finding.message` + `finding.file` (concatenated). No match → skip row.
3. Match: record annotation with the row's regulations. Set `annotator: "pattern-table"`.
4. If `llm_review_trigger: true`, invoke the `compliance-edge-annotator` agent for this finding only. The agent can refine citations, add or remove regulations, or add a judgment note. Set `annotator: "llm"` if the agent modified anything.

A finding with zero matching rows gets no annotation and does NOT appear in the output.

### 3. LLM call counting (for eval)

The skill exposes an optional `LLMCallCounter` interface for eval assertions:

```python
class LLMCallCounter:
    def invoke(self, prompt: str, context: dict) -> str: ...
    def count(self) -> int: ...
    def reset(self) -> None: ...
```

Production dispatches go through a real LLM. Eval runs inject a mock counter and assert the count matches the expected number of `llm_review_trigger: true` matches in the fixture.

### 4. Write output

Write `memory/compliance-<slug>.json` with the disclaimer at the root. The exec-report-generator includes the disclaimer verbatim in the report header.

## Disclaimer (exact wording, required on every report)

> This compliance mapping is informational and derived from pattern matching. It does not constitute a certified audit and should not be used as a substitute for formal compliance review.

## Invariants

- Pattern table is the source of truth. LLM never invents citations; it only refines or annotates table-matched citations.
- LLM call count is bounded: one call per finding with `llm_review_trigger: true`. No loops, no recursion.
- Schema-invalid pattern rows fail the run. No silent skipping.
- Every annotation carries `annotator: "pattern-table" | "llm"` for audit.
- The disclaimer appears verbatim in every compliance output. Downstream must not strip it.

## Related

- `agents/compliance-edge-annotator.md` — the sonnet-tier agent invoked for `llm_review_trigger: true` matches
- `knowledge/compliance-patterns.yaml` — the pattern table itself
- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` — unified finding envelope
