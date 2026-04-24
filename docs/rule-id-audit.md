# Rule ID dedup audit — `security-review` agent vs. `agentic-security-review` plugin rulesets

**Date**: 2026-04-24
**Scope**: All detection output that lands in the unified-finding envelope defined by `plugins/agentic-dev-team/knowledge/security-primitives-contract.md`
**Goal**: Identify overlap zones where the same vulnerability class is detected by both the `security-review` agent (dev-team plugin) and one or more semgrep rules (custom rulesets in this plugin + community rulesets it invokes), and classify each overlap as *dedup-safe*, *dedup-gap*, or *coverage-gap*.

## Executive summary

Three findings:

1. **Blocker: agent findings have no `rule_id`.** The agent's output schema (`plugins/agentic-dev-team/agents/security-review.md:10-14`) emits `{status, issues: [{severity, confidence, file, line, message, suggestedFix}], summary}` — no `rule_id` field. The unified-finding envelope requires `rule_id` (`security-primitives-contract.md` Envelope 2). No adapter in `plugins/agentic-dev-team/skills/static-analysis-integration/` normalizes agent output into the unified envelope. The `security-review.*` namespace does not appear anywhere in the codebase. Consequence: agent findings either (a) never reach the unified stream, or (b) reach it with an undefined `rule_id`, breaking the fp-reduction dedup key (`rule_id + metadata.source_ref`; `fp-reduction.md:57`).
2. **Dedup gap: pattern-visible classes.** For ~11 vulnerability classes the agent grep-detects AND the plugin has a semgrep rule for, even once #1 is fixed the two rule_ids will differ (e.g. `security-review.A03.sql-injection` vs `semgrep.javascript.typeorm-sqli`). The dedup key won't match, producing two findings for one underlying issue.
3. **Coverage gap: agent covers classes with no plugin rule.** ~8 vulnerability classes are only in the agent's `owasp-detection.md`. If the rules-vs-prompts policy promotes any of these to rules, corresponding semgrep rules need to be added.

## Rule_id namespacing today

| Producer | Namespace | Source |
|---|---|---|
| Community semgrep `p/security-audit` | `semgrep.<lang>.<rule-slug>` | External ruleset |
| Community semgrep `p/owasp-top-ten` | `semgrep.<lang>.<rule-slug>` | External ruleset |
| Plugin custom rulesets (7 files) | `<ruleset>.<vendor?>.<rule>` (see below) | `knowledge/semgrep-rules/*.yaml` |
| gitleaks | `gitleaks.generic.<rule>` | via adapter |
| hadolint | `hadolint.dockerfile.<code>` | via adapter |
| actionlint | `actionlint.yaml.<code>` | via adapter |
| trivy config | `trivy.config.<check>` | via adapter |
| `security-review` agent | **UNDEFINED** | — |

### Plugin custom rule IDs (36 rules across 7 rulesets)

```text
crypto-anti-patterns.node-tls-reject-unauthorized
crypto-anti-patterns.openssl-legacy-provider
crypto-anti-patterns.python-verify-false
crypto-anti-patterns.non-aead-cipher
crypto-anti-patterns.pip-trusted-host-wildcard
crypto-anti-patterns.md5-for-integrity

datastore.cassandra.consistency-level-mismatch
datastore.cassandra.toctou-optimistic-lock
datastore.mongodb.unauthenticated-upsert
datastore.redis.user-controlled-key
datastore.sql.string-format-injection

fraud-domain.fail-open-scoring
fraud-domain.client-controlled-aggregate-feature
fraud-domain.emulation-mode-bypass
fraud-domain.tokenization-skip-under-flag

llm-safety.hardcoded-api-key
llm-safety.prompt-template-string-injection
llm-safety.untrusted-tool-response-used
llm-safety.insecure-model-download

messaging.nats.subject-injection
messaging.nats.no-auth-config
messaging.nats.hardcoded-credentials
messaging.nats.unauthenticated-subscriber
messaging.kafka.no-auth-producer
messaging.general.no-idempotency-check

ml-patterns.insecure-pickle-load
ml-patterns.unverified-onnx-load
ml-patterns.torch-load-untrusted
ml-patterns.model-from-url

serialization.java.kryo-unsafe-deserialization
serialization.python.unsafe-deserialization
serialization.python.onnx-metadata-injection
serialization.python.mongodb-nosql-injection
serialization.java.objectinputstream-unsafe
serialization.python.model-feature-name-injection
serialization.javascript.model-feature-name-injection
```

## Overlap matrix (by OWASP category from `owasp-detection.md`)

Legend: **🔴 dedup-gap** = both fire, different rule_ids; **🟡 coverage-gap** = agent-only; **🟢 no-overlap** = plugin-only

| OWASP | Agent pattern | Plugin rule(s) | Community rule (likely) | Dedup status |
|---|---|---|---|---|
| A01 | Missing auth middleware (JS/TS) | — | — | 🟡 coverage-gap (agent-only; judgment class) |
| A01 | Missing `[Authorize]` (C#) | — | — | 🟡 coverage-gap (judgment class) |
| A01 | Missing `@PreAuthorize` (Java) | — | — | 🟡 coverage-gap (judgment class) |
| A01 | IDOR | — | — | 🟡 coverage-gap (judgment class) |
| A01 | Path traversal | — | `semgrep.*.path-traversal-*` in `p/security-audit` | 🔴 dedup-gap |
| A02 | Weak hashing MD5/SHA1 for passwords | — | `semgrep.*.weak-hash-*` in `p/security-audit` | 🔴 dedup-gap (plus `crypto-anti-patterns.md5-for-integrity` overlaps partial) |
| A02 | Hardcoded keys regex | — | `semgrep.generic.hardcoded-*` in community + `llm-safety.hardcoded-api-key` | 🔴 dedup-gap (3-way: agent + community + custom) |
| A02 | `ServerCertificateValidationCallback=>true` (C#) | — | `semgrep.csharp.cert-validation-disabled` in community | 🔴 dedup-gap |
| A02 | `Math.random()` for tokens (JS/TS) | — | `semgrep.javascript.weak-random` | 🔴 dedup-gap |
| A02 | `new Random()` for tokens (C#) | — | `semgrep.csharp.insecure-random` | 🔴 dedup-gap |
| A02 | `java.util.Random` for tokens | — | `semgrep.java.insecure-random` | 🔴 dedup-gap |
| A03 | SQL injection (JS/TS template literals) | `datastore.sql.string-format-injection` | `semgrep.javascript.raw-sql-*` in `p/security-audit` | 🔴 3-way dedup-gap |
| A03 | SQL injection (C# `FromSqlRaw`) | `datastore.sql.string-format-injection` | `semgrep.csharp.raw-sql` | 🔴 3-way dedup-gap |
| A03 | SQL injection (Java concat `createQuery`) | `datastore.sql.string-format-injection` | `semgrep.java.sql-string-concat` | 🔴 3-way dedup-gap |
| A03 | XSS `innerHTML` / `dangerouslySetInnerHTML` | — | `semgrep.javascript.xss-*` | 🔴 dedup-gap |
| A03 | XSS `Html.Raw()` (C#) | — | `semgrep.csharp.html-raw` | 🔴 dedup-gap |
| A03 | Command injection `exec/spawn` | — | `semgrep.*.command-injection-*` | 🔴 dedup-gap |
| A03 | Template injection | — | Varies by engine | 🔴 dedup-gap |
| A04 | No rate limiting on auth | — | — | 🟡 coverage-gap (judgment class) |
| A04 | No brute force protection | — | — | 🟡 coverage-gap (judgment class) |
| A04 | Missing CSRF (C# POST without `[ValidateAntiForgeryToken]`) | — | `semgrep.csharp.missing-antiforgery` | 🔴 dedup-gap |
| A05 | `DEBUG=true`, `NODE_ENV` not checked | — | `semgrep.javascript.debug-env-*` (partial) | 🔴 dedup-gap (partial) |
| A05 | `<DebugType>full</DebugType>` in Release | — | — | 🟡 coverage-gap |
| A05 | Permissive CORS `*` / `AllowAnyOrigin()` | — | `semgrep.*.cors-wildcard-*` | 🔴 dedup-gap |
| A05 | Missing CSP/HSTS/X-Frame-Options | — | — | 🟡 coverage-gap (often handled by headers libraries; plugin has nothing custom) |
| A05 | Default credentials `admin/admin` | — | `semgrep.generic.default-credentials` (partial) | 🔴 dedup-gap |
| A05 | Verbose errors / `UseDeveloperExceptionPage()` in prod | — | `semgrep.csharp.developer-exception-page` | 🔴 dedup-gap |
| A06 | Vulnerable dependencies | — (agent delegates to `npm audit` etc.) | `trivy fs --scanners vuln` via adapter | 🟢 no-overlap (trivy authoritative) |
| A07 | Weak password hashing `bcrypt` cost<10 | — | `semgrep.*.bcrypt-low-cost` | 🔴 dedup-gap |
| A07 | JWT `algorithms: ['none']` | — | `semgrep.*.jwt-alg-none` | 🔴 dedup-gap |
| A07 | JWT no `exp` claim | — | — | 🟡 coverage-gap (judgment class; hard to pattern-match) |
| A07 | Session fixation (ID not regenerated after login) | — | — | 🟡 coverage-gap (judgment class) |
| A07 | Insecure cookie (missing Secure/HttpOnly/SameSite) | — | `semgrep.*.insecure-cookie-*` | 🔴 dedup-gap |
| A08 | `BinaryFormatter`, `TypeNameHandling.All` (C#) | `serialization.*` (partial) | `semgrep.csharp.binary-formatter` | 🔴 3-way dedup-gap |
| A08 | `ObjectInputStream` (Java) | `serialization.java.objectinputstream-unsafe` | `semgrep.java.deserialization-*` | 🔴 3-way dedup-gap |
| A08 | `eval()`, `Function()` (JS/TS) | — | `semgrep.javascript.eval-injection` | 🔴 dedup-gap |
| A09 | PII in logs `password/ssn/creditCard/token` | — | — | 🟡 coverage-gap (judgment class per-field; could be a rule) |
| A09 | No auth event logging | — | — | 🟡 coverage-gap (judgment class) |
| A09 | Sensitive data in error messages | — | — | 🟡 coverage-gap (judgment class) |
| A10 | User-controlled URLs in `fetch`/`HttpClient` | — | `semgrep.*.ssrf-*` | 🔴 dedup-gap |
| A10 | Internal network access (`169.254.169.254`) | — | `semgrep.*.cloud-metadata-ssrf` | 🔴 dedup-gap |

### Tally

- **🔴 Dedup gaps**: 25 classes (semgrep rule exists; agent will double-report if its findings land in the unified stream)
- **🟡 Coverage gaps**: 12 classes (agent-only; could be rule candidates per the policy)
- **🟢 No overlap**: 1 (dependency vulns, trivy authoritative)

Plus the plugin's 36 custom rules cover **no-overlap** areas the agent doesn't touch:

- Cassandra consistency/TOCTOU (5 rules) — none in agent
- Kafka/NATS messaging auth (6 rules) — none in agent
- LLM safety runtime patterns (4 rules) — none in agent
- ML model loading (4 rules) — none in agent
- Python-specific serialization (multiple) — partial agent coverage
- Crypto-anti-patterns cluster (6 rules) — thin agent coverage

## Recommendations

In order of leverage:

1. **Fix the agent rule_id gap (blocker).** Add a `rule_id` field to the agent's output schema, namespaced `security-review.A<NN>.<slug>` where `<NN>` is the OWASP category and `<slug>` is the pattern. Wire an adapter in `plugins/agentic-dev-team/skills/static-analysis-integration/` (or directly in the orchestrator for `/security-assessment`) that emits the unified finding envelope from agent output. Without this, dedup is undefined regardless of the overlap matrix.
2. **Decide the policy for pattern-visible classes** (this is the separate `docs/rules-vs-prompts-policy.md` deliverable). The 25 🔴 entries are the candidate set for "strip from agent, rely on plugin rule".
3. **Add coverage rules for 🟡 classes that are genuinely pattern-visible** — candidates include PII-in-logs field names (A09), hardcoded default credentials (A05), and insecure-cookie flags (A07) if not already covered by community rules.
4. **Document dedup-key conventions** in `security-primitives-contract.md`. Today the spec says dedup is applied at exec-report-generator, but the rule_id-namespace alignment across producers is implicit. State explicitly that (a) all producers MUST emit `rule_id` in the unified envelope; (b) when two producers detect the same class, the adapter responsible for agent output SHOULD adopt the corresponding semgrep rule_id rather than minting its own namespace entry — so dedup collapses them.

## Open questions

- Q1: Is the agent's JSON output ever actually transformed into unified-finding envelope format today, or does Phase 1b emit findings in a different channel? Read `commands/security-assessment.md` or the orchestrator to confirm. If findings don't enter the unified stream at all, the dedup concern is theoretical until they do.
- Q2: Should `security-review.*` rule_ids cite the corresponding semgrep rule when one exists (single-namespace dedup), or live in a parallel namespace and rely on a dedup-alias table? The former is simpler; the latter preserves provenance.
- Q3: Community rulesets (`p/security-audit`, `p/owasp-top-ten`) emit rule_ids that the plugin doesn't own. Dedup across the agent ↔ community pair requires either (a) the agent adopts community rule_ids when applicable, or (b) an alias table maintained in the plugin. Decide.
