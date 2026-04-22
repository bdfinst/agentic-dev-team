# Cross-Repository Security Summary

**Assessment date:** 2026-04-21
**Scope:** `repos/fraud-scoring/` + `repos/auth-gateway/` + shared CI at `repos/fixture-shared/ci.yml`

---

## 1. Executive Overview

**Combined Risk Rating: CRITICAL.** Two services designed as a fraud-scoring pipeline are deployed with no authentication on any endpoint, a fraud model that fails open, a gateway that issues admin tokens to anonymous callers, and a shared signing secret committed to both repos. BlackDuck / SCA tooling would report only unpinned dependencies — every CRITICAL finding in this assessment is in a class no SCA tool can detect.

| Metric | Value |
|--------|------:|
| Total findings (post-dedup) | **29** |
| Critical | **7** |
| High | **12** |
| Medium | **7** |
| Low | **3** |
| Findings suppressed by business-logic carveouts | 3 |
| Shared-secret clusters | 1 (`JWT_SECRET`) |
| Unauthenticated endpoints | 6 of 6 (100%) |

### Headline pattern
Both services ship the same architectural assumption: "something upstream of us does auth." Nothing in either repo does. The result is a fraud scoring pipeline that approves every request it is asked about — trivially via Chain B (see §4), or more creatively via emulation mode, exception-driven fail-open, or model swap.

---

## 2. Top 10 Findings Across Both Repos (Ranked)

| Rank | ID | Title | Sev | Repo | CWE |
|:---:|----|-------|:-:|------|-----|
| 1 | FS-C-01 | Fail-open on scorer exception | CRITICAL | fraud-scoring | 755 |
| 2 | FS-C-03 | Client-controlled aggregate features | CRITICAL | fraud-scoring | 807 |
| 3 | AG-C-01 | Unauthenticated admin-token mint | CRITICAL | auth-gateway | 306 + 269 |
| 4 | FS-C-04 | Unauthenticated `/admin/reload-model` | CRITICAL | fraud-scoring | 306 |
| 5 | X-01 | Shared JWT signing secret across repos | CRITICAL | both | 798 |
| 6 | FS-C-02 | `EMULATION_MODE` env-var bypass | CRITICAL | fraud-scoring | 489 |
| 7 | FS-C-05 | AWS + DB + JWT credentials in prod env file | CRITICAL | fraud-scoring | 798 |
| 8 | X-06 | TLS verification disabled across egress paths | HIGH | both | 295 |
| 9 | FS-H-03 | ONNX model loaded without integrity check | HIGH | fraud-scoring | 494 |
| 10 | X-02 | Upstream forwarding trust boundary missing | HIGH | both | 441 |

---

## 3. Shared Credential Inventory

| Value | Type | Locations | Sev |
|-------|------|-----------|:-:|
| `Welcome2ACI-shared-2026` | JWT signing secret | `fraud-scoring/config/.env.production:6`, `auth-gateway/config/.env.staging:3` | CRITICAL |
| `NODE_TLS_REJECT_UNAUTHORIZED=0` | TLS-disable flag | `fraud-scoring/config/.env.production:9`, `auth-gateway/src/server.ts:10` | HIGH |
| `fallback-secret-for-dev` | JWT fallback literal | `auth-gateway/src/routes/admin.ts:15` | HIGH |
| `postgres://fraud:fraud@db.internal/fraud` | DB creds | `fraud-scoring/config/.env.production:11` | HIGH |
| `AKIAIOSFODNN7EXAMPLE` / `wJalrXUtnFEMI/…KEY` | AWS access keys | `fraud-scoring/config/.env.production:2-3` | CRITICAL |

**Systemic pattern:** production credentials live in `config/.env.*` files, are committed to the repo, and are baked into Docker images via `COPY . .`. There is no evidence of a secrets manager, no `.gitignore` entry for env files, and no `.dockerignore`.

---

## 4. Attack Chain Analysis

### Chain A — Shared secret → admin token forgery
1. Attacker reads `Welcome2ACI-shared-2026` from `fraud-scoring/config/.env.production:6` (or the auth-gateway copy).
2. `POST /admin/issue-token` on auth-gateway with `{"email":"x"}` returns a signed `{sub:x, role:admin}` JWT.
3. Every service in the organization that currently or later trusts `JWT_SECRET=Welcome2ACI-shared-2026` accepts that token.
**Severity:** CRITICAL. Real today on auth-gateway; pre-positioned for fraud-scoring.

### Chain B — Anonymous feature poisoning → fraud approval (zero-credential path)
1. `curl -X POST http://auth-gateway:3000/score -d '{"amount": 100000, "velocity_24h": 0, "count_last_1h": 0}'`.
2. auth-gateway `/score` handler forwards body verbatim with TLS-check disabled (`server.ts:10,28-31`).
3. fraud-scoring `/predict` copies `velocity_24h` and `count_last_1h` from body into the feature vector (`features.py:17-22`).
4. Score is low; `/predict` returns `decision: allow` (`server.py:45`).
**Severity:** CRITICAL. Single request, no credentials, fraud approved.

### Chain C — Emulation mode turns the scorer into a rubber stamp
1. Malicious PR (or compromised CI) sets `EMULATION_MODE=1` on the fraud-scoring deployment.
2. The shared CI workflow runs `semgrep` with `continue-on-error: true` (`fixture-shared/ci.yml:18-21`), then deploys with `contents: write` permission.
3. `scorer.score_transaction` returns `0.1` for every request (`scorer.py:24-25`).
**Severity:** CRITICAL.

### Chain D — Model swap via unauth reload + zero-valued hash file
1. Attacker obtains write access to `MODEL_PATH` (any mount misconfiguration or traversal).
2. Calls `POST /admin/reload-model` (no auth) (`server.py:18-23`).
3. `onnx.load(path)` runs with no integrity verification (`scorer.py:15`); the `.sha256` file is zero-valued placeholder.
**Severity:** CRITICAL.

### Chain E — CI secret exfiltration via `printenv`
1. `fixture-shared/ci.yml:17` runs `printenv` inside a GitHub Actions job.
2. Logs capture every env var; tolerated by the `continue-on-error` security step.
3. The deploy job has `contents: write` and `id-token: write` — enough for a supply-chain poisoning step to land in the image.
**Severity:** HIGH.

### Chain F — TLS-off + shared internal network = eavesdropping & tampering
1. auth-gateway sets `NODE_TLS_REJECT_UNAUTHORIZED = "0"` at module import.
2. Every outbound `fetch` to `https://fraud-scoring.internal:8000` ignores cert errors.
3. Any pod/VM on the same internal network can MITM the proxy flow and observe/modify scoring requests and decisions.
**Severity:** HIGH.

---

## 5. Systemic Issues (Organizational Patterns)

| # | Pattern | Evidence |
|---|---------|----------|
| SYS-1 | **Zero-auth architecture.** No middleware, no `jwt.verify`, no API key checks on any of 6 routes. | server.py:{18,27,34}, server.ts:28, admin.ts:{8,14} |
| SYS-2 | **Fail-open by default.** Exception handler approves transactions; no circuit breaker. | server.py:43, server.ts:28-31 |
| SYS-3 | **No secrets management.** Credentials committed + image-baked; shared across repos. | `.env.*`, Dockerfiles |
| SYS-4 | **TLS verification disabled everywhere.** Runtime env var, explicit `verify=False`, pip `--trusted-host *`. | .env.production:9, server.ts:10, crypto_utils.py:16, Dockerfile:6 |
| SYS-5 | **No integrity checks on runtime artifacts.** ONNX model, base images, pip+npm packages, all mutable. | scorer.py:15, Dockerfile tags, requirements.txt, package.json |
| SYS-6 | **CI is cosmetic.** Security scan runs with `continue-on-error: true`; auth-gateway has no CI build step at all. | fixture-shared/ci.yml |
| SYS-7 | **Hidden debug/emulation paths in production.** `EMULATION_MODE` env switch; `"fallback-secret-for-dev"` literal. | scorer.py:24, admin.ts:15 |

---

## 6. Regulatory Compliance Gaps

### PCI-DSS

| Requirement | Gap | Affected Finding(s) |
|------------|-----|---------------------|
| 3.4 — Render PAN unreadable | PAN logged at DEBUG | FS-H-04 |
| 4.1 — Strong cryptography during transmission | TLS verification globally disabled | X-06 |
| 6.3 — Review code for vulnerabilities prior to release | `continue-on-error` on security scan | S06-SHARED-02 |
| 6.4.4 — No test data/accounts in production | `"fallback-secret-for-dev"` in prod path | AG-H-04 |
| 8.2.1 — Strong authentication credentials | All endpoints unauthenticated | FS-C-04, AG-C-01, AG-H-01/02 |
| 8.3 — MFA for admin | No auth at all, let alone MFA | SYS-1 |
| 10.3 — Audit logging | No audit logging for admin actions | SYS-1 |

### GDPR

| Article | Gap | Affected |
|---------|-----|----------|
| Art. 5(1)(c) Data minimisation | Email in JWT payload; full PAN in debug logs | FS-H-04, AG-L-01 |
| Art. 32 Security of processing | TLS off, fail-open, zero-auth | X-06, FS-C-01, SYS-1 |

### SOX ITGC

- Deploy pipeline grants `contents: write` with no approval gate; no traceable change control for prod deploys (S06-SHARED-03).

---

## 7. Consolidated Remediation Roadmap

### Priority 1 — Immediate (48 hours)
| Action | Finding(s) | Owner |
|--------|-----------|-------|
| Rotate `JWT_SECRET` + AWS keys + DB creds + Slack webhook; move all to secrets manager | X-01, FS-C-05, FS-H-06, AG-H-05 | Security |
| Gate or delete `/admin/issue-token` and all admin endpoints | AG-C-01, AG-H-01, FS-C-04, FS-H-01 | Dev + Security |
| Fail-close the scorer exception handler (`return allow` → `raise HTTPException(503)`) | FS-C-01 | Dev |
| Remove `NODE_TLS_REJECT_UNAUTHORIZED=0` at runtime and in env files | X-06 | Dev + DevOps |

### Priority 2 — Urgent (2 weeks)
| Action | Finding(s) | Owner |
|--------|-----------|-------|
| Put an authenticating gateway in front of both services (`jwt.verify` middleware + upstream mTLS) | X-02, FS-H-02, AG-H-02/03 | Architecture + Dev |
| Remove `EMULATION_MODE` branch; server-side compute aggregate features | FS-C-02, FS-C-03 | Dev |
| Verify ONNX model hash on load; replace zero-valued `.sha256` with a real one | FS-H-03, FS-M-04 (partial) | Dev + MLOps |
| Add `USER app` to final Dockerfile stages in both repos | FS-H-05, AG-H-06 | DevOps |
| Commit `package-lock.json`, switch to `npm ci`; pin pip deps with hashes; drop `--trusted-host *` | FS-H-7/8, AG-H-07, AG-M-03 | DevOps |
| Remove `printenv`, `continue-on-error` on security step, narrow `contents: write` | S06-SHARED-01/02/03 | DevOps + Security |

### Priority 3 — Important (30 days)
| Action | Finding(s) | Owner |
|--------|-----------|-------|
| Replace MD5 + AES-CBC; drop `verify=False` | FS-M-01/02/03 | Dev |
| Add algorithm + expiry to `jwt.sign`; opaque `sub` | AG-M-01, AG-L-01 | Dev |
| Digest-pin base images in both Dockerfiles; add SBOM emission | FS-L-01, AG-M-02 | DevOps |
| Add timeouts / retries / circuit breaker on every outbound call | FS-L-02, AG-M-04, AG-L-03 | Dev |
| Mask PAN in logs; drop default log level to `INFO`; no body logging | FS-H-04 | Dev |

### Priority 4 — Strategic (90 days)
| Action | Finding(s) | Owner |
|--------|-----------|-------|
| Service mesh with mTLS between gateway and scoring; zero-trust defaults | X-02, SYS-4 | Architecture |
| Central secrets manager integration; remove every `.env.*` committed file | SYS-3 | Architecture + Security |
| Feature-flag system replacing raw env-var toggles | SYS-7 | Architecture |
| CI overhaul: add SAST/DAST/SCA/container scan gates that **fail the build**; add auth-gateway build step | SYS-6, S06-SHARED-04, S06-AG-01 | DevOps + Security |

---

## 8. Methodology

- **Pipeline:** 9-pass static analysis (secrets, AuthZ, business logic, PII/PCI, infrastructure, CI/CD, crypto, supply chain, concurrency) × 2 repos = 18 scan passes, plus Phase 2 cross-repo correlation and Phase 3 5-stage FP reduction. See `results/scans/` for raw outputs.
- **Carveouts honored:** `business_logic.md` §1 (test fixture credentials) and §2 (multi-stage Dockerfile builder stage).
- **Files analyzed:** 17 source + config + infra files, 1 shared CI workflow, 2 carveout policy files. See per-repo report Appendix B for full file inventories.
- **Limitations:** No DAST; no runtime/cluster inspection; no git-history forensics (no `.git/` in the fixture); no binary inspection of the ONNX artifact.

### Top 3 organization-wide actions (read-twice-click-once)
1. **Stop shipping credentials in the repo.** Delete `config/.env.production` and `config/.env.staging`; never `COPY . .` without a `.dockerignore`; adopt a secrets manager.
2. **Put authentication in front of everything.** Six endpoints, zero auth. Fix that before any other remediation.
3. **Fail closed, not open.** On any scoring error, exception, or missing config, the answer is "deny" + alert — not a fixed "allow" with a benign score.
