---
name: false-positive-reduction
description: Hybrid FP-reduction skill — joern call-graph when present, LLM fallback when absent. Five-stage rubric applied to every unified finding before it reaches the exec report. Emits the disposition register defined in security-primitives-contract.md v1.1.0.
role: worker
user-invocable: false
version: 1.0.0
maintainers:
  - bdfinst
  - unassigned
required-primitives-contract: ^1.0.0
---

# False-Positive Reduction (hybrid joern + LLM)

## Purpose

Transform a stream of unified findings into a disposition register that the exec-report-generator can trust. Every finding gets a verdict (`true_positive | likely_true_positive | uncertain | likely_false_positive | false_positive`), a reachability trace, an exploitability score, and a reachability_source tag (`joern-cpg` or `llm-fallback`).

The skill's job is to remove noise without suppressing real issues. False positives waste analyst attention; missed true positives get someone fired.

## Five-stage rubric (applied in order; each stage can downgrade severity or change verdict)

Lifted from the `opus_repo_scan_test` reference's § analyze-11 framework with extensions for the disposition-register output format.

### Stage 1 — Reachability

**Question**: Is this code executed in production at all?

Disposition rules:
- Dead code (no inbound call graph from any entry point) → `verdict: false_positive`, severity → `info` presentational.
- Test-only paths (only reached from test code) → `verdict: likely_false_positive`, severity → one level down (CRITICAL → HIGH, HIGH → MEDIUM).
- Feature-flagged-off in all production configs → one level down, verdict stays `true_positive`.
- Reached from production entry point → no change; record the entry point in `reachability.rationale`.

Joern-present mode: reachability is computed from the CPG by tracing back from the finding location to HTTP/CLI/lambda/cron entry points.

Joern-absent mode: the agent reasons from RECON's `entry_points` and `security_surface` fields, plus grep over the call sites. Tag each entry with `reachability_source: llm-fallback`.

### Stage 2 — Environment context

**Question**: Could deployed configuration override the committed value, making the finding inert?

Disposition rules:
- Confirmed override at deploy time (e.g. env var in `values.yaml` or Helm chart overrides a committed default) → one level down, `verdict: likely_true_positive` (the committed value is still a weak default).
- No override found → full severity, verdict unchanged.

The agent consults `docker-compose*.yml`, `values.yaml`, `helmfile.yaml`, `k8s/*.yaml`, and any CI-scoped env vars discoverable in `.github/workflows/*` or GitLab equivalents.

### Stage 3 — Compensating controls

**Question**: Is there a control in the repo that mitigates this finding's impact?

Disposition rules:
- Confirmed in-repo control (WAF rule, rate limiter, input validation layer upstream of the finding, idempotency key check, etc.) → one level down, verdict `likely_true_positive` with the control's file:line in the rationale.
- Assumed-only ("we have a WAF in prod" — not verifiable from the repo) → no change.
- Absent → no change.

### Stage 4 — Deduplication

**Question**: Is this the same root cause as another finding already in the register?

Disposition rules:
- Same rule_id + same value (e.g. same secret SHA-256) across multiple files → collapse to ONE finding with a `locations` array; emit one disposition entry referencing the primary finding.
- Same rule_id + different values (e.g. 14 different hardcoded passwords) → separate findings, NOT deduplicated.
- Different rule_ids that describe the same root cause (e.g. `semgrep.python.hardcoded-password` + `gitleaks.generic.aws-access-key` firing on the same line) → dedupe keeping the higher-priority source per the static-analysis skill's priority order.

### Stage 5 — Severity calibration

**Question**: Is the severity consistent across similar findings?

Disposition rules:
- Ensure two findings with identical exploitability profiles receive identical presentational severity across the run.
- If a finding falls between two severity levels, prefer the higher — better to over-flag than miss. Use exploitability score (0–10) to break ties deterministically per the severity-mapping table in the primitives contract.

## Exploitability scoring (0–10)

Per-finding score determines presentational severity bucket (see primitives contract § Severity mapping). Factors:

| Factor | Weight | Example |
|---|---|---|
| Network reachability | +3 | Finding is in an HTTP handler on a public route |
| Authentication bypass | +3 | Finding bypasses an auth check (not merely missing one) |
| Credential exposure | +2 | Finding leaks a credential an attacker could use elsewhere |
| Input-controlled | +2 | An attacker can influence the vulnerable value via request parameters |
| Persistent | +1 | Finding creates persistent state (stored XSS, stored credentials) |
| Privileged context | +1 | Finding runs in an elevated context (root, admin route) |
| Cascading | +1 | A successful exploit unlocks further access (lateral movement) |

Rationale field is mandatory (min 20 chars per schema). Summarize which factors applied and why.

## Joern integration (when present)

If `joern` is on PATH, invoke via `tools/reachability.sh`:

```bash
joern-parse "$REPO" --output "$CACHE/$COMMIT.cpg"
joern-export --repr cfg --format json "$CACHE/$COMMIT.cpg" > "$CACHE/$COMMIT.cfg.json"
```

The CPG is cached per commit SHA under `memory/joern-cache/<sha>.cpg` if build time exceeds 30s.

Stage 1 reachability queries the CPG for paths from the finding location back to entry points. Each finding's `reachability.rationale` cites the entry point path.

## LLM-fallback mode (joern absent)

Stages 1–3 use judgment rather than CPG data. Stages 4–5 work unchanged.

**Every disposition entry produced in fallback mode carries `reachability_source: llm-fallback`.** The exec-report-generator detects this tag and emits a Section 0 banner (verbatim):

> Reachability stage used LLM reasoning instead of call-graph analysis; dead-code paths may be less accurate. Stages 2–5 unaffected.

## Output

A `DispositionRegister` object per the schema at `plugins/agentic-dev-team/knowledge/schemas/disposition-register-v1.json`. Contains:

- `schema_version: "1.0"` (contract envelope remains 1.0; primitives contract can be 1.1.0 — the envelope schema does not version lock-step with the contract)
- `generated_at` ISO-8601
- `dispositioner: "fp-reduction"`
- `reachability_tool: joern-cpg | llm-fallback` (register-level default; entries can override)
- `entries[]`: one per finding

Register is written to `memory/disposition-<assessment-slug>.json`.

## Related

- `agents/fp-reduction.md` — the opus agent that implements this skill
- `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` — disposition register schema + severity mapping
- `plugins/agentic-dev-team/knowledge/schemas/disposition-register-v1.json` — JSON Schema
- `tools/reachability.sh` — joern wrapper (installed if joern is on PATH)
