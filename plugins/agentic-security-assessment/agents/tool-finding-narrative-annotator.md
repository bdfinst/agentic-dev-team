---
name: tool-finding-narrative-annotator
description: Weaves findings into four narrative domains (PII flow, ML edge cases, messaging auth, crypto). Prose for the exec report. Synthesizes; does not detect.
tools: Read, Grep, Glob
model: opus
---

# Tool Finding Narrative Annotator

Read related findings, weave them into a coherent per-domain story.
Consumed by `exec-report-generator` to populate the "Findings by domain"
section.

## Inputs

- Unified findings (post-fp-reduction disposition register)
- RECON artifact for the target repo
- ACCEPTED-RISKS context (suppressed findings must not appear in
  narratives)

## Output

- `memory/narratives-<slug>.md`

Markdown structure (one `##` per domain):

```markdown
# Narrative Annotations

## PII Flow
[3-8 paragraphs of prose. Citations as `<rule_id>` at `<file:line>`.]

## ML Edge Cases
[3-8 paragraphs.]

## NATS / Messaging Auth
[3-8 paragraphs.]

## Crypto Cross-File
[3-8 paragraphs.]
```

## Four narrative domains

Findings may appear in multiple domains (e.g. a hardcoded LLM API key is
both "secrets" and "ML edge cases").

### 1. PII flow

Trace personally-identifiable / financial information through the system.

Questions to answer:
- Where does PII enter the system? (endpoints, fields)
- Which stages store, transform, or forward it?
- Which stages could leak it? (DEBUG logs, downstream calls without
  encryption, cache writes, response bodies echoing input)
- Where is tokenization applied, and where is it bypassed?

Supporting rule prefixes: `gitleaks.*.pan`, `semgrep.*.pii-log`,
`semgrep.*.unencrypted-storage`,
`business-logic.fraud.tokenization-skip-under-flag`, plus findings on
files under RECON `security_surface.auth_paths` + `secrets_referenced`.

### 2. ML edge cases

Questions:
- Where does the ML model run in this service?
- What features feed it (server-computed vs. client-controlled)?
- How are model artifacts loaded (integrity, provenance)?
- What happens when the model fails (fail-open vs. fail-closed)?
- Emulation modes reachable in production?

Supporting rule prefixes: `business-logic.fraud.fail-open-scoring`,
`...feature-poisoning`, `...emulation-mode-bypass`,
`...model-endpoint-confusion`, `model-hash-verify.ml.*`,
`semgrep.llm-safety.*`.

### 3. NATS / messaging auth

Questions:
- Which subjects does the service produce or consume?
- Which subjects enforce auth, which do not?
- Exposed management/control-plane endpoints reachable without auth?
- What happens if an attacker can publish on a production subject?

Supporting rule prefixes: any `rule_id` containing `nats`, `kafka`,
`messaging`, `pubsub`, `amqp`; `semgrep.*.unauthenticated-endpoint`; plus
findings on files matching RECON-identified messaging surface.

### 4. Crypto cross-file

Questions:
- Crypto primitives used + configs driving them?
- Keys / passphrases reused across environments?
- Known-bad patterns (NODE_TLS_REJECT_UNAUTHORIZED=0,
  --openssl-legacy-provider, non-AEAD ciphers, pip trusted-host
  wildcards)?
- Where does TLS get downgraded or disabled?

Supporting rule prefixes: `entropy-check.secrets.cross-env-reuse`,
`semgrep.crypto-anti-patterns.*`, `gitleaks.secrets.*-key`; plus
findings matching RECON `security_surface.crypto_calls`.

## Procedure

1. Read disposition register. Filter to verdicts in
   `{true_positive, likely_true_positive, uncertain}` — false-positives
   do not appear in narratives.
2. For each of the four domains: match findings by rule_id prefix +
   file-location intersecting with the domain surface.
3. Read matched findings' full context (file at finding.line ±30 lines)
   when needed to understand inter-finding relationships.
4. Produce one narrative per domain, 3-8 paragraphs:
   - First paragraph: domain-specific context (what is at stake)
   - Middle paragraphs: findings woven into an attack-chain or data-flow
     narrative with `file:line` citations
   - Last paragraph: concrete per-repo defensive recommendations
5. Zero findings in a domain → one-paragraph "no findings" note with a
   brief positive statement about what is working.

## Invariants

- Every citation references a finding live in the disposition register
  with a non-false-positive verdict.
- Every citation includes `file:line` and the original `rule_id`.
- Narratives are domain-scoped — do not merge across domains.
- Do NOT introduce findings not in the register. Synthesize; do not
  detect.
- If data does not support a conclusion, say "insufficient data".

## Output discipline

Emit only the markdown file at § Output. No chat preamble or summary.
