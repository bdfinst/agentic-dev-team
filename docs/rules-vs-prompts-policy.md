# Policy: when a vulnerability class belongs in a semgrep rule vs. an agent prompt

**Status**: draft for review
**Date**: 2026-04-24
**Applies to**: `plugins/agentic-dev-team/agents/security-review.md` (agent prompt) and `plugins/agentic-security-assessment/knowledge/semgrep-rules/*.yaml` (custom rulesets) plus their interaction with community rulesets (`p/security-audit`, `p/owasp-top-ten`).

## Why this exists

The `security-review` agent and the companion plugin's rulesets currently duplicate coverage on ~25 vulnerability classes (see `docs/rule-id-audit.md`). Duplication without a principled boundary means every new pattern costs work in both places and every missed update produces a coverage asymmetry. This policy draws the line.

## The boundary

A vulnerability class belongs in a **semgrep rule** when BOTH are true:

1. **Syntactically stable.** The vulnerability presents as a single-line regex, a fixed-shape AST, or a deterministic small pattern that survives reasonable code-style variation.
2. **Low false-positive rate.** Measured or expected false-positive rate is **≤10%** on a representative fixture suite. (If no fixture suite exists yet, the rule author must build one before the rule ships.)

A vulnerability class belongs in the **agent prompt** when ANY is true:

- Detection requires reasoning over multiple files or call sites.
- Detection requires knowledge of authz architecture, session lifecycle, or per-request state.
- Detection requires business-domain context that can't be encoded as a pattern (e.g., "this route exposes PII in a context where it shouldn't").
- The false-positive rate with a pattern alone is above 10%, but LLM judgment over the same pattern drops it below 10%.
- The class is about *exploitability assessment* of a finding already produced by a rule (rules detect; agent judges impact).

## Tie-breakers

- **If a community rule exists** (`p/security-audit` or `p/owasp-top-ten`) covering the class with acceptable FP rate, prefer it over adding a custom rule or keeping it in the agent prompt. No custom work; inherit upstream maintenance.
- **If a community rule exists but has >10% FP on fraud/ML/edge targets**, add a narrower custom rule and document the reason in YAML frontmatter. Both can ship; the unified-finding dedup collapses them if rule_ids align.
- **If a pattern is stable in language A but judgment-class in language B** (e.g., SQL concat is pattern-detectable in Python but requires framework awareness in Java JPA), put each language in the surface where it belongs. One class can have a rule for A and an agent prompt for B.

## What this means concretely

### Classes that should move to rules (candidates to strip from `owasp-detection.md`)

These have corresponding plugin or community rules today and are pattern-stable (see `docs/rule-id-audit.md`):

- MD5/SHA1 for security purposes (A02)
- Hardcoded keys regex (A02) — but keep the agent's ability to assess exploitability when a rule fires
- `Math.random()` / `new Random()` / `java.util.Random` for security tokens (A02)
- SQL concat in `createQuery` / `prepareStatement` without `?` (A03)
- XSS via `innerHTML` / `dangerouslySetInnerHTML` / `Html.Raw()` (A03)
- `BinaryFormatter`, `TypeNameHandling.All` (A08)
- `ObjectInputStream` (A08)
- `eval()` / `Function()` (A08)
- Missing CSRF token attribute (A04) — if framework-native, stays as agent
- Permissive CORS wildcard (A05)
- JWT `algorithms: ['none']` (A07)

### Classes that stay in the agent prompt

These are judgment classes:

- Missing auth middleware on a route (requires understanding routing + auth)
- Missing `[Authorize]` / `@PreAuthorize` (requires understanding application tier)
- IDOR (requires understanding ownership model)
- No rate limiting (architectural)
- No brute force protection (architectural)
- JWT no `exp` claim (requires token-creation context)
- Session fixation (requires login-flow analysis)
- PII in logs (requires classifying fields as PII)
- Verbose errors / stack traces (requires production-vs-dev context)
- Default credentials detection (contextual; `admin/admin` is obvious but domain-specific defaults need LLM)

### Classes that belong in both (detection + judgment)

Some classes have a rule that detects the pattern AND an agent that assesses exploitability. This is NOT duplication — it's a pipeline:

- Rule fires → unified finding in stream
- Agent does NOT re-detect; instead, agent uses the finding as input and assesses whether the specific call is reachable, whether the input is user-controlled, whether the context amplifies risk
- Agent output goes to `fp-reduction`'s disposition register, not to a duplicate finding

This is how semgrep + the agent should interoperate once the rule_id gap in the audit is closed.

## Maintenance cadence

- **Quarterly**: walk the overlap matrix in `docs/rule-id-audit.md`; for each 🔴 dedup-gap, verify rule_ids still align across producers. File issues for drift.
- **Per-PR**: any new pattern added to `owasp-detection.md` OR to a plugin ruleset must be evaluated against this policy. Reviewer should reject adds to the wrong surface.
- **On community ruleset update**: re-measure FP rates on the internal fixture suite; adjust custom rules or agent patterns if FP thresholds are newly exceeded / newly cleared.

## Fixture suite expectation

Each custom rule in `plugins/agentic-security-assessment/knowledge/semgrep-rules/*.yaml` must ship with:

- At least one **positive fixture** (file containing the pattern; rule must fire)
- At least one **negative fixture** (file with similar-shape code that should NOT fire; rule must not fire)
- Baseline measured FP rate on the fixture suite, recorded in the ruleset YAML frontmatter as `fp_rate: <decimal>`

When the 10% threshold is exceeded, the rule is demoted to the agent prompt surface (judgment class) until the rule can be tightened.

## Rule_id namespacing

The agent emits findings with `rule_id` fields in the unified finding envelope via the adapter at `plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py`. Pattern-visible classes adopt upstream rule_ids (e.g. `semgrep.generic.sql-injection`); judgment-only classes use the `security-review.a<NN>.<slug>` namespace. The canonical mapping lives at `plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml`.

Cross-source dedup collapse (agent + semgrep on the same issue) works because the adapter adopts upstream rule_ids, matching fp-reduction's Stage 4 collapse key `rule_id + file + line` (`plugins/agentic-security-assessment/agents/fp-reduction.md:57`).

## Out of scope

- Red-team probe interpretation (lives in `plugins/agentic-security-assessment/agents/redteam-*.md`). Those agents are narrative synthesizers over tool output, not detectors.
- Compliance mapping. The compliance skill does a different job (regulatory mapping) and doesn't participate in the rules-vs-prompts debate.
- Dependency-vulnerability scanning. Trivy is authoritative; neither rules nor prompts reproduce that.

## Open questions for reviewer

- **Q1**: Is the ≤10% FP threshold the right bar, or should it be stricter for certain categories (e.g., 5% for A07 auth classes where noise erodes trust)?
Answer: the ≤10% FP threshold is right
- **Q2**: Should the policy be enforced by a CI check (e.g., `scripts/audit-rules-vs-prompts.sh` that walks `owasp-detection.md` patterns and flags any whose signature matches a plugin rule by heuristic)? Or is quarterly manual review sufficient?
Answer: quarterly manual review sufficient
- **Q3**: When the agent prompt is trimmed of pattern-visible classes, should those removed sections be replaced with short pointers to the corresponding rule (`# MD5: covered by crypto-anti-patterns.md5-for-integrity`), or removed entirely? Pointers aid discoverability at the cost of noise in the prompt.
Answer: replaced with short pointers to the corresponding rule
- **Q4**: Community rule_id alignment — adopt upstream rule_ids in the agent adapter (single namespace, easy dedup) or maintain an alias table in the plugin (more provenance-friendly)?
Answer: adopt upstream rule_ids
