---
name: domain-logic-patterns
description: Reference catalogue of ML/fraud business-logic anti-patterns. Consumed by the business-logic-domain-review agent as a detection-cue reference. Not a detection engine itself.
version: 1.0.0
maintainers:
  - bdfinst
  - unassigned
---

# Domain logic patterns (ML / fraud services)

Reference catalogue of seven business-logic anti-patterns the `business-logic-domain-review` agent hunts for. Each entry expands the cues with concrete code signatures (for greps) and example exploit scenarios.

Patterns validated by the `opus_repo_scan_test` reference's `scan-03-business-logic-fraud.md` agent against three production ACI data-science repos.

## Shared attack model

The attacker can submit transactions through the same public API endpoints a legitimate caller uses. They cannot modify server code, but they can:

- Control request bodies, headers, and URL parameters
- Observe response times and content
- Submit many requests (rate-limited, not throttled to zero)
- Correlate request/response pairs over time

Anything the server trusts from a client-controlled field is a potential manipulation vector.

## 1. Fail-open scoring

**Grep cues:**
```
try:\s*$\n.*predict|score|model\.
except[^\n]*:\s*$\n[^\n]*return.*(allow|accept|approve|0\.0|false|{|\[)
catch\s*\([^)]*\)\s*{[^}]*return[^;}]*(allow|accept|approve)
```

**Confirming context**: the error path returns a success-shape payload rather than an error shape. Check the response schema — if the fail-open path returns a valid `{"decision": ..., "score": ...}` object, the consumer cannot distinguish "model failed" from "model said allow".

**Exploit scenario**: attacker forces a model timeout (overlong feature vector, adversarial input that triggers a rare codepath) and the endpoint returns `allow` by default. Fraud gets scored as legitimate.

**Remediation pointer**: error path must return an error shape OR fail-closed (deny by default + alert). Never default to allow.

## 2. Score manipulation / client-controlled features

**Grep cues:**
```
features\[['"].*['"]\]\s*=\s*request\.|request\.(body|json|form)\.\w+
features\.append\(request
model\.predict\(.*request\.(body|json)
```

**Confirming context**: walk the data flow from `request` to `predict`. If any feature in the prediction vector is assigned directly from request data without lookup/validation, that feature is attacker-controlled.

**Exploit scenario**: attacker submits `{"velocity_24h": 1, "prior_chargebacks": 0}` where these should be server-computed. Low fraud score returned.

## 3. Emulation-mode bypass

**Grep cues:**
```
(os\.environ|os\.getenv|process\.env)\.?get?\(['"]?(EMULATION|TEST|DEMO|MOCK|STUB)_MODE
request\.headers\.get\(['"]?X-(Test|Emulate|Mock|Bypass)
if\s+.*(EMULATION|TEST|DEMO)_MODE.*:\s*\n.*return\s+(stub|mock|canned|test)
```

**Confirming context**: the flag controls a short-circuit in the scoring path, not just response logging. If setting the flag causes the function to skip `model.predict(...)` entirely, that is emulation-mode.

**Exploit scenario**: attacker sets `X-Test-Mode: true` on a production endpoint. If the server reads it and routes to the stub, fraud gets a canned "not fraud" score.

## 4. Model-endpoint confusion

**Grep cues:**
```
@app\.(post|get)\(['"]/.*predict
@router\.(post|get)\(['"]/.*score
app\.(post|get)\(['"]/.*(predict|score)
```

**Confirming context**: if multiple prediction routes exist, compare their threshold logic. An attacker who can aim high-risk traffic at the low-threshold endpoint wins.

**Exploit scenario**: `/v1/predict` applies threshold 0.7; `/v2/predict-fast` applies threshold 0.9. Attacker routes high-risk traffic to v2.

## 5. Tokenization / PII-masking skip

**Grep cues:**
```
if\s+.*(SKIP|BYPASS|DISABLE)_?(TOKEN|MASK|PROTEGRITY)
if\s+config\.\w*(skip|bypass|disable)
if\s+request\.headers\.get\(['"]X-Raw-PAN
```

**Confirming context**: the path protected by the flag contains raw PAN / PII / card-number handling. The flag disables the protection step, not just the logging.

**Exploit scenario**: attacker finds the internal header that bypasses tokenization; logs now contain raw PAN.

## 6. Feature poisoning

**Grep cues:**
```
features\[['"](\w*velocity|\w*count|\w*aggregate|\w*sum)['"]\]\s*=\s*request\.
features\.get_or_compute\(
if\s+request\.body\.get\(['"]\w*velocity.*:\s*\n.*features
```

**Confirming context**: features named with aggregate-shape words (velocity, count, sum, rate, avg, max, last_24h, last_1h) should be server-computed. If the code has a path that reads them from the request instead, that is poisoning.

**Exploit scenario**: attacker submits legitimate feature fields plus a `velocity_24h: 1` override. Legitimate low-velocity features get high weight; fraud score drops.

## 7. Missing replay idempotency

**Grep cues:**
```
# Look for the ABSENCE of:
request\.headers\.get\(['"]Idempotency-Key
cache\.get\(transaction_id\)
deduplicate|replay_protection|already_seen
```

**Confirming context**: at the scoring entry point, check whether an idempotency key or transaction ID is consulted before scoring. If the same body submitted twice scores differently (due to timing-dependent features), replay is possible.

**Exploit scenario**: attacker submits the same fraud transaction body repeatedly. Early submissions might score as fraud; later ones might score as legitimate once timing-dependent features reset. Attacker retries until a low score is returned, then that becomes the recorded decision.

## Ordering

The `business-logic-domain-review` agent walks files in order of likelihood of hosting these patterns:

1. Files under RECON's `security_surface.auth_paths`
2. Files with `score`, `fraud`, `predict`, `model`, `decision`, `risk` in their path
3. Files under `handlers/`, `routes/`, `controllers/`, `api/` directories
4. Everything else (only checked if the above produced no findings — low likelihood)

## Out of scope

These patterns do NOT catch:

- Adversarial inputs (evasion attacks — the red-team harness covers this at runtime, not statically)
- Model extraction (also red-team)
- Numerical features where a valid large value masquerades as manipulation (cannot distinguish statically from pattern alone)
- Multi-service attack chains (that is `cross-repo-synthesizer`'s job)
