# Security Assessment — fraud-scoring

**Assessment date:** 2026-04-21
**Scope:** `repos/fraud-scoring/` (Python 3.10 / FastAPI / ONNX)
**Methodology:** 9-pass static analysis pipeline + cross-repo correlation + 5-stage false-positive reduction (see Section 5).

---

## Section 0 — Executive Summary

**Overall Risk Rating: CRITICAL.** The service has no authentication on any of its three endpoints, fails open to "approve" on any scoring error, and reads the very features it scores against from the user's own request — i.e., an attacker tells it whether they are a fraudster.

- **An attacker can approve fraudulent transactions without credentials.** The `/predict` endpoint has no login, no API key, no gateway token. An attacker submits a transaction and the scorer approves it — either by supplying benign-looking feature values, by triggering an exception (the service returns "allow" on every error), or by flipping the service into "emulation mode" (a hardcoded low score for every caller).
- **The model file has no integrity verification.** An attacker who can write the model file — or who can drop a file at a path the service treats as the model — can take over every decision. An "integrity hash" file sits next to the model but contains only zeros and is never checked.
- **Sensitive information is logged at DEBUG in production.** The log configuration turns on DEBUG globally; card numbers pass through the request path. Anyone with log access reads plaintext PANs.
- **Credentials are committed to the repo and shipped inside the container.** AWS keys, a database URL with the password "fraud", and a JWT secret that is *shared with the auth-gateway service* all live in `config/.env.production` and are baked into every image.
- **The container runs as root and the build disables TLS verification.** The final image has no `USER` directive; `pip install` runs with `--trusted-host *`, which turns off certificate checks for package downloads.

**Compared to a BlackDuck scan:** BlackDuck would report only the unpinned-dependencies finding (S08-FS-01). Every other item in this report — all five CRITICAL fraud-bypass findings — is out of scope for an SCA tool and requires the static-analysis pipeline.

**Top 3 Immediate Actions (48 hours):**
1. Rotate `JWT_SECRET`, AWS keys, and database credentials, and move them into a secrets manager (not the repo, not the image).
2. Put an authenticating reverse proxy in front of `POST /predict`, `POST /admin/reload-model`, and `GET /actuator/heap` before the service is exposed externally.
3. Replace the `try/except → return allow` block at `src/server.py:43` with a fail-closed response (`503 + decision: deny`).

---

## Section 1 — Findings Dashboard

Summary: **5 Critical | 8 High | 4 Medium | 3 Low | Total: 20**

| ID | Title | Severity | Category | CWE |
|----|-------|:-:|----------|-----|
| FS-C-01 | Fail-open on scorer exception | CRITICAL | Business Logic | CWE-755 |
| FS-C-02 | `EMULATION_MODE` env-var bypass | CRITICAL | Business Logic | CWE-489 |
| FS-C-03 | Client-controlled aggregate features | CRITICAL | Business Logic | CWE-807 |
| FS-C-04 | Unauthenticated admin endpoint (model reload) | CRITICAL | AuthZ | CWE-306 |
| FS-C-05 | AWS access keys hardcoded in production env file | CRITICAL | Secrets | CWE-798 |
| FS-H-01 | Unauthenticated `/actuator/heap` | HIGH | AuthZ | CWE-306 |
| FS-H-02 | Unauthenticated `/predict` (model oracle) | HIGH | AuthZ | CWE-306 |
| FS-H-03 | ONNX model loaded without integrity check | HIGH | ML Integrity | CWE-494 |
| FS-H-04 | DEBUG-level logging of PAN | HIGH | PII/PCI | CWE-532 |
| FS-H-05 | Final container image runs as root | HIGH | Infrastructure | CWE-250 |
| FS-H-06 | Database credentials with weak value | HIGH | Secrets | CWE-798 |
| FS-H-07 | `pip install --trusted-host *` disables TLS | HIGH | Supply Chain | CWE-295 |
| FS-H-08 | Python dependencies fully unpinned | HIGH | Supply Chain | CWE-1357 |
| FS-M-01 | MD5 used for integrity hashing | MEDIUM | Crypto | CWE-327 |
| FS-M-02 | `httpx.get(..., verify=False)` | MEDIUM | Crypto | CWE-295 |
| FS-M-03 | AES-CBC without HMAC | MEDIUM | Crypto | CWE-353 |
| FS-M-04 | Secrets copied into Docker image layers | MEDIUM | Infrastructure | CWE-538 |
| FS-L-01 | Base image tag-pinned, not digest-pinned | LOW | Supply Chain | CWE-494 |
| FS-L-02 | Unsynchronised `_model` state | LOW | Concurrency | CWE-362 |
| FS-L-03 | No network policy / k8s isolation declared | LOW | Infrastructure | CWE-1008 |

---

## Section 2 — Critical & High Findings (Detailed)

### FS-C-01: Fail-open on scorer exception

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | Business Logic / Fraud Domain |
| CWE | CWE-755 — Improper Handling of Exceptional Conditions |

**Description:** On any exception raised inside `score_transaction`, the handler logs the error and returns `{"decision":"allow","score":0.0}`. There is no business reason to approve a transaction whose scoring failed.

**File:** `src/server.py:38-43`

**Code Evidence:**
```python
try:
    score = score_transaction(features)
except Exception as e:
    log.error(f"scoring failed: {e}")
    # SEED: F010 (scan-03 business-logic) — fail-open: returns low score on error
    return {"decision": "allow", "score": 0.0}
```

**Business Impact:** An attacker who can cause *any* exception inside scoring — a malformed input, a model reload mid-request, a dependency outage — receives a successful fraud approval. This single branch is the single largest latent fraud-bypass in the codebase.

**Attack Scenario:**
1. Attacker POSTs `{"amount": "not-a-number", ...}` to `/predict`.
2. `float(...)` inside `build_feature_vector` raises `ValueError`.
3. Exception propagates; handler returns `decision: allow`.
4. Fraud check is bypassed for every malformed request.

**Remediation:**
```python
try:
    score = score_transaction(features)
except Exception:
    log.exception("scoring failed")
    raise HTTPException(status_code=503, detail="scoring unavailable")
```
Default **deny** on the caller side; never approve on error.

**False Positive Assessment:** Reachable from every POST to `/predict`; the entire service has only this one scoring endpoint, so the exception path is a hot path. No compensating control. CONFIRMED.

---

### FS-C-02: `EMULATION_MODE` env-var bypass

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | Business Logic / Hidden Functionality |
| CWE | CWE-489 (Active Debug Code) / CWE-912 (Hidden Functionality) |

**Description:** `scorer.score_transaction` short-circuits to a hardcoded `0.1` score whenever the `EMULATION_MODE` env var is set. No feature flag system, no allowlist, no log warning.

**File:** `src/scorer.py:23-25`

**Code Evidence:**
```python
if os.environ.get("EMULATION_MODE"):
    return 0.1  # stub score; short-circuits real scoring in prod if env set
```

**Business Impact:** Any operational or supply-chain avenue that sets an env var on the deployment (compromised CI, accidental override, malicious config PR) disables the fraud model organization-wide.

**Attack Scenario:**
1. Attacker opens a PR modifying the deployment manifest to set `EMULATION_MODE=1`.
2. The shared CI (see CI findings in cross-repo report) has `continue-on-error: true` on the security scan and grants `contents: write` to the deploy job.
3. Merge lands; next rollout ships the env var.
4. Every `/predict` returns score 0.1 → below the 0.7 threshold → `decision: allow`.

**Remediation:** Remove the branch entirely from production code. If emulation is needed for testing, move it behind an import-time build flag that is not present in the production wheel.

**False Positive Assessment:** Reachable — the check runs before the real scoring path. No override removes it. CONFIRMED.

---

### FS-C-03: Client-controlled aggregate features

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | Business Logic / Fraud Feature Poisoning |
| CWE | CWE-807 — Reliance on Untrusted Inputs in a Security Decision |

**Description:** `build_feature_vector` reads `velocity_24h` and `count_last_1h` directly from the request body. These features are meant to describe the caller's history and must be computed server-side from authoritative data.

**Files:** `src/features.py:17-22` (both aggregate features, one root cause)

**Code Evidence:**
```python
features["velocity_24h"] = body.get("velocity_24h", 0.5)
features["count_last_1h"] = body.get("count_last_1h", 0.5)
```

**Business Impact:** An attacker that knows any of these feature names sets them to innocuous values and trivially scores below the 0.7 fraud threshold. There is no feature whose value the scorer cares about that the user cannot set.

**Attack Scenario:**
1. Attacker POSTs `{"amount": 99999, "velocity_24h": 0, "count_last_1h": 0}` to `/predict`.
2. Score sums to a low value; response is `decision: allow`.
3. Fraud approved with no friction.

**Remediation:** Compute aggregate features from a server-side store keyed by an authenticated session/identifier. Reject any request whose body attempts to set those keys.

**False Positive Assessment:** Active on every request. No override. CONFIRMED.

---

### FS-C-04: Unauthenticated admin endpoint (model reload)

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | AuthZ / Missing Authentication |
| CWE | CWE-306 |

**Description:** `POST /admin/reload-model` runs `onnx.load(MODEL_PATH)` without any authentication check. Combined with FS-H-03 (no integrity verification) this is a full model-swap gadget.

**File:** `src/server.py:18-23`

**Code Evidence:**
```python
@app.post("/admin/reload-model")
async def admin_reload_model():
    """Reloads the scoring model. No auth check."""
    from .scorer import reload_model
    reload_model()
    return {"status": "reloaded"}
```

**Business Impact:** Anyone reachable to the service can force model reloads — both as a DoS (thrash the load) and, with any write path to `MODEL_PATH`, as a total model takeover.

**Attack Scenario:**
1. Attacker gains write access to the model path via a mounted volume or filesystem traversal.
2. Attacker POSTs `/admin/reload-model` — server reads the attacker's ONNX file without verification.
3. All subsequent `/predict` calls use the attacker model; it is trained to always return 0.

**Remediation:** Require a bearer token (or at minimum, listen on a Unix socket not reachable externally). Verify the model file against a signed hash before load.

**False Positive Assessment:** Route registration is unconditional at import time. CONFIRMED.

---

### FS-C-05: AWS access keys hardcoded in production env file

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | Secrets Management |
| CWE | CWE-798 |

**Description:** `config/.env.production` commits an AWS access key pair, a JWT secret shared with auth-gateway, and a database URL with embedded credentials. The file is read by the service at startup and also baked into image layers via `COPY . .`.

**File:** `config/.env.production:2-3,6,11`

**Code Evidence:**
```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
JWT_SECRET=Welcome2ACI-shared-2026
DATABASE_URL=postgres://fraud:fraud@db.internal/fraud
```

**Business Impact:** Any rotation of these placeholders will land a live secret in the repo and all historical image tags. The current AWS values are documented placeholders, but the slot is a production credential slot — the JWT secret and DB password are live, low-entropy, and shared.

**Attack Scenario:**
1. Attacker clones repo (or `docker pull` any tagged image).
2. Extracts `config/.env.production`.
3. Forges JWTs valid for both services (CWE-798 + shared secret).
4. Connects to `db.internal` with `fraud:fraud`.

**Remediation:** Delete the committed env file. Manage production secrets via Vault / AWS Secrets Manager / External Secrets Operator. Add `config/.env.*` to `.gitignore` and `.dockerignore`.

**False Positive Assessment:** File is committed and image-baked; no deploy-time substitution pattern present. CONFIRMED. Note: the JWT secret is deduplicated into cross-repo finding X-01.

---

### FS-H-01: Unauthenticated `/actuator/heap`

**Severity:** HIGH — **CWE-306** — **File:** `src/server.py:27-31`

Information disclosure (object counts leak internal state) + DoS vector (`gc.get_objects()` is O(N)). Remediation: remove the endpoint or gate behind an admin-only route at an isolated port.

---

### FS-H-02: Unauthenticated `/predict` (model oracle)

**Severity:** HIGH — **CWE-306** — **File:** `src/server.py:34-45`

Any unauth caller can query the fraud model, enabling model extraction and adversarial probing. Remediation: require an authenticated upstream gateway (auth-gateway does NOT currently authenticate callers — see cross-repo report).

---

### FS-H-03: ONNX model loaded without integrity verification

**Severity:** HIGH — **CWE-494** — **Files:** `src/scorer.py:11-15`, `models/scoring-v1.onnx.sha256`

```python
path = os.environ.get("MODEL_PATH", "/app/models/scoring-v1.onnx")
_model = onnx.load(path)
```
The hash file sits next to the model but is zero-valued and never read. **Remediation:**
```python
expected = open(path + ".sha256").read().strip()
actual = hashlib.sha256(open(path, "rb").read()).hexdigest()
if actual != expected:
    raise RuntimeError("model integrity check failed")
_model = onnx.load(path)
```

---

### FS-H-04: DEBUG-level logging of PAN

**Severity:** HIGH — **CWE-532** — **File:** `src/logging_config.py:8-14`

`logging.basicConfig(level=logging.DEBUG)` is unconditional; a helper logs `pan=<value>` at DEBUG. PCI-DSS 3.4 violation. Remediation: `logging.INFO` minimum in production, mask PAN before logging, and never log last 12 digits.

---

### FS-H-05: Final container image runs as root

**Severity:** HIGH — **CWE-250** — **File:** `Dockerfile:9-19`

No `USER` directive in the `python:3.10-slim` stage. Carveout §2 covers the builder stage only. **Remediation:**
```dockerfile
RUN useradd -u 10001 app && chown -R app /app
USER app
```

---

### FS-H-06: Database credentials with weak value

**Severity:** HIGH — **CWE-798** — **File:** `config/.env.production:11`

`postgres://fraud:fraud@db.internal/fraud` — password equals username. Remediation: rotate to a secrets-manager-supplied 32-byte value and connect with `sslmode=require`.

---

### FS-H-07: `pip install --trusted-host *` disables TLS

**Severity:** HIGH — **CWE-295** — **File:** `Dockerfile:6`

```dockerfile
RUN pip install --trusted-host * -r requirements.txt
```
Disables certificate validation for *every* package index. **Remediation:** remove the flag; if a private index is needed use `--index-url https://… --trusted-host pypi.internal` (narrowly scoped).

---

### FS-H-08: Python dependencies fully unpinned

**Severity:** HIGH — **CWE-1357** — **File:** `requirements.txt:2-6`

All five deps listed with no version, no hash. Combined with FS-H-07 the build is fully non-deterministic and fetched over unverified TLS. **Remediation:** `pip-compile` to `requirements.lock` with `--generate-hashes`; install with `--require-hashes`.

---

## Section 3 — Medium & Low Findings (Condensed)

### FS-M-01: MD5 used for integrity hashing — MEDIUM
**CWE-327** | `src/crypto_utils.py:10-11`
MD5 is collision-broken. **Remediation:** replace with `hashlib.sha256`.

### FS-M-02: `httpx.get(..., verify=False)` — MEDIUM
**CWE-295** | `src/crypto_utils.py:14-17`
TLS verification disabled on a signature-fetch helper. **Remediation:** remove the `verify=False` kwarg.

### FS-M-03: AES-CBC without HMAC — MEDIUM
**CWE-353** | `src/crypto_utils.py:20-23`
Non-AEAD cipher mode. **Remediation:** switch to `AES.MODE_GCM` with a 96-bit nonce and return `(nonce, ciphertext, tag)`.

### FS-M-04: Secrets copied into Docker image layers — MEDIUM
**CWE-538** | `Dockerfile:12`
`COPY . .` bakes `config/.env.production` and `tests/` into the image. **Remediation:** add `.dockerignore` with `config/.env.*`, `tests/`, `*.sha256`.

### FS-L-01: Base image tag-pinned, not digest-pinned — LOW
**CWE-494** | `Dockerfile:2,9`
**Remediation:** pin to `python:3.10-slim@sha256:…`.

### FS-L-02: Unsynchronised `_model` state — LOW
**CWE-362** | `src/scorer.py:8-21`
**Remediation:** guard reload under a `threading.Lock`; swap atomically.

### FS-L-03: No network policy / k8s isolation declared — LOW
**CWE-1008** | repo root (absent)
**Remediation:** Add a Helm chart with a default-deny `NetworkPolicy`.

---

## Section 4 — Remediation Roadmap

### Priority 1 — Immediate (48 hours)

| Action | Findings | Owner |
|--------|----------|-------|
| Rotate AWS keys, JWT secret, DB password; move to Vault / AWS Secrets Manager | FS-C-05, FS-H-06 | Security + Dev |
| Put an authenticating proxy (or upstream gateway auth) in front of all three routes | FS-C-04, FS-H-01, FS-H-02 | DevOps + Security |
| Replace `try/except → return allow` with `raise HTTPException(503)` | FS-C-01 | Dev |

### Priority 2 — Urgent (2 weeks)

| Action | Findings | Owner |
|--------|----------|-------|
| Remove `EMULATION_MODE` branch from production build | FS-C-02 | Dev |
| Server-side compute `velocity_24h` / `count_last_1h`; reject body-supplied values | FS-C-03 | Dev |
| Verify ONNX model hash on load; populate `.sha256` correctly or remove it | FS-H-03 | Dev + MLOps |
| Mask PAN in logs; set default log level to `INFO` | FS-H-04 | Dev |
| Add `USER app` to final Dockerfile stage | FS-H-05 | DevOps |
| Remove `--trusted-host *`; pin + hash dependencies | FS-H-07, FS-H-08 | DevOps |
| Add `.dockerignore` for secrets + tests | FS-M-04 | DevOps |

### Priority 3 — Important (30 days)

| Action | Findings | Owner |
|--------|----------|-------|
| Replace MD5 with SHA-256; AES-CBC with AES-GCM; drop `verify=False` | FS-M-01, FS-M-02, FS-M-03 | Dev |
| Digest-pin base images; add SBOM generation | FS-L-01, (S08-FS-02) | DevOps |
| Synchronise model-swap state under a lock | FS-L-02 | Dev |

### Priority 4 — Strategic (90 days)

| Action | Findings | Owner |
|--------|----------|-------|
| Introduce a service mesh with mTLS between gateway and scoring | FS-L-03 + X-02 | Architecture |
| Adopt a feature-flag system for all "emergency" toggles (no raw env-var switches) | FS-C-02 pattern | Architecture |

---

## Section 5 — Methodology & Scope

**Pipeline:** 9-pass static analysis driven by `agents/scan-*.md` markdown prompts (secrets, AuthZ, business logic, PII/PCI, infrastructure, CI/CD, crypto, supply chain, concurrency). Phase 0 recon produced `results/scans/RECON-fraud-scoring.md`; scans 01–09 produced `results/scans/fraud-scoring-scan-0N-*.md`; Phase 3 disposition in `results/scans/analyze-11-false-positive-reduction.md`.

**Limitations:** No DAST; no runtime testing; no binary inspection of the ONNX artifact (zero-byte placeholder); no live endpoint probing (that is the scope of the companion `adversarial-agents/` pipeline).

**Files analyzed:** see Appendix B.

---

## Appendix A — Secrets Inventory

| Secret | Type | Location(s) | Rotation Status |
|--------|------|-------------|-----------------|
| `AKIAIOSFODNN7EXAMPLE` | AWS access key id | `config/.env.production:2` | Rotate + move to secrets manager |
| `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` | AWS secret key | `config/.env.production:3` | Rotate + move to secrets manager |
| `Welcome2ACI-shared-2026` | JWT secret (shared) | `config/.env.production:6` | Rotate + split per-service |
| `postgres://fraud:fraud@…` | DB URL with creds | `config/.env.production:11` | Rotate + sslmode=require |
| `NODE_TLS_REJECT_UNAUTHORIZED=0` | TLS disable flag | `config/.env.production:9` | Remove |
| `test-fixture-api-key-abc123` | Test fixture | `tests/test_scorer.py:6` | **Suppressed** per business_logic.md §1 |
| `test-jwt-secret-xyz789` | Test fixture | `tests/test_scorer.py:7` | **Suppressed** per business_logic.md §1 |

## Appendix B — File Inventory

| File | Lines | Risk Level | Notes |
|------|------:|-----------|-------|
| `src/server.py` | 45 | **CRITICAL** | 3 unauth routes + fail-open |
| `src/scorer.py` | 29 | **CRITICAL** | Emulation bypass + onnx.load no verify |
| `src/features.py` | 24 | **CRITICAL** | Client-controlled aggregate features |
| `src/crypto_utils.py` | 23 | **HIGH** | MD5, verify=False, CBC |
| `src/logging_config.py` | 16 | **HIGH** | DEBUG root logger + PAN logger |
| `config/.env.production` | 12 | **CRITICAL** | 4 live credentials |
| `Dockerfile` | 19 | **HIGH** | Root user, trusted-host *, no digest pin |
| `requirements.txt` | 8 | **HIGH** | Unpinned |
| `tests/test_scorer.py` | 14 | suppressed | Accepted-risks carveout §1 |
| `models/scoring-v1.onnx.sha256` | 1 | **MEDIUM** | Zero-valued placeholder |
| `models/scoring-v1.onnx` | binary | INFO | Not inspected |
