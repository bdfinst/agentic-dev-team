# Security Assessment — auth-gateway

**Assessment date:** 2026-04-21
**Scope:** `repos/auth-gateway/` (TypeScript / Node.js 20 / Express 4)
**Methodology:** 9-pass static analysis pipeline + cross-repo correlation + 5-stage false-positive reduction.

---

## Section 0 — Executive Summary

**Overall Risk Rating: CRITICAL.** The service calls itself "auth-gateway" but performs no authentication. Its signature endpoint mints admin-role JSON Web Tokens for any anonymous caller.

- **Anyone can issue themselves an admin token.** The endpoint `POST /admin/issue-token` takes an email from the request body and returns a signed token that says "you are an admin". There is no login, no password, no anything.
- **TLS certificate checking is turned off at process start.** The service blindly accepts any certificate on every outbound call it makes. An attacker on the internal network can intercept traffic to the fraud-scoring service.
- **A secret key is shared with the other service.** The token-signing key is the same string that lives in the fraud-scoring service's production configuration. One compromise = both services forgeable.
- **If the environment variable holding the secret is not set, the service silently falls back to a hardcoded string.** Any deploy that forgets to inject `JWT_SECRET` will sign tokens with `"fallback-secret-for-dev"`.
- **The container runs as root.** As with the other service, there is no `USER` directive on the final Docker image.

**Compared to a BlackDuck scan:** BlackDuck would report only the unpinned npm dependencies (S08-AG-01). The privilege-escalation gadget, the TLS-off setting, the hardcoded fallback secret, and the lack of any `jwt.verify` call would all be invisible to SCA.

**Top 3 Immediate Actions (48 hours):**
1. Remove `process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"` at `src/server.ts:10`.
2. Replace the `/admin/issue-token` handler with an authenticated admin flow, OR remove the endpoint entirely if no admin issuance is needed.
3. Rotate `JWT_SECRET`, move it into a secrets manager, and remove the `"fallback-secret-for-dev"` literal (make the env var required at boot).

---

## Section 1 — Findings Dashboard

Summary: **1 Critical | 6 High | 4 Medium | 3 Low | Total: 14**

| ID | Title | Severity | Category | CWE |
|----|-------|:-:|----------|-----|
| AG-C-01 | Unauthenticated admin-token mint | CRITICAL | AuthZ / Privilege Escalation | CWE-306 + CWE-269 |
| AG-H-01 | Unauthenticated `/admin/flush-cache` | HIGH | AuthZ | CWE-306 |
| AG-H-02 | Unauthenticated `/score` proxy | HIGH | AuthZ / Open Proxy | CWE-441 |
| AG-H-03 | `jwt.verify` never called anywhere | HIGH | AuthN | CWE-287 |
| AG-H-04 | Hardcoded JWT fallback secret | HIGH | Secrets / Crypto | CWE-798 |
| AG-H-05 | Slack webhook URL committed | HIGH | Secrets | CWE-798 |
| AG-H-06 | Final container image runs as root | HIGH | Infrastructure | CWE-250 |
| AG-H-07 | npm dependencies unpinned | HIGH | Supply Chain | CWE-1357 |
| AG-M-01 | No algorithm/expiry specified on `jwt.sign` | MEDIUM | Crypto | CWE-1188 + CWE-613 |
| AG-M-02 | Secrets baked into image layers | MEDIUM | Infrastructure | CWE-538 |
| AG-M-03 | `npm install` used instead of `npm ci` | MEDIUM | Supply Chain | CWE-1357 |
| AG-M-04 | No timeout/retry/circuit-breaker on upstream fetch | MEDIUM | Resilience | CWE-730 |
| AG-L-01 | Email PII carried in JWT payload | LOW | PII | CWE-359 |
| AG-L-02 | `dotenv` dep listed but never imported | LOW | Supply Chain | CWE-1104 |
| AG-L-03 | Unhandled promise rejection on `/score` | LOW | Concurrency | CWE-754 |

---

## Section 2 — Critical & High Findings (Detailed)

### AG-C-01: Unauthenticated admin-token mint

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| Category | AuthZ / Privilege Escalation |
| CWE | CWE-306 (Missing Auth) + CWE-269 (Improper Privilege Management) |

**Description:** `POST /admin/issue-token` is mounted under an unauthenticated router and hardcodes `role: "admin"` on every token it signs. Combines with AG-H-04 (fallback secret) and X-01 (shared secret across repos).

**File:** `src/routes/admin.ts:14-18`

**Code Evidence:**
```ts
adminRoutes.post("/issue-token", (req, res) => {
    const secret = process.env.JWT_SECRET ?? "fallback-secret-for-dev";
    const token = jwt.sign({ sub: req.body.email, role: "admin" }, secret);
    res.json({ token });
});
```

**Business Impact:** The gateway is the mint. Any anonymous caller receives a signed admin token valid for every downstream service that trusts this service's tokens (today: potentially fraud-scoring, which shares the signing secret). There is no rate limit, no captcha, no audit.

**Attack Scenario:**
1. Attacker sends `curl -X POST http://auth-gateway/admin/issue-token -d '{"email":"a"}'`.
2. Response contains a signed `{"sub":"a","role":"admin"}` JWT.
3. Attacker presents that token to any service (today or in a future rollout) that expects `JWT_SECRET=Welcome2ACI-shared-2026` or the fallback literal.
4. Attacker is treated as admin with no other checks.

**Remediation:**
```ts
import { requireAdminAuth } from "./middleware.js";
adminRoutes.post("/issue-token",
    requireAdminAuth,          // JWT-verified admin call
    (req, res) => {
        if (!process.env.JWT_SECRET) throw new Error("JWT_SECRET required");
        const token = jwt.sign(
            { sub: req.body.email, role: req.body.role },  // role approved by caller
            process.env.JWT_SECRET,
            { algorithm: "HS256", expiresIn: "15m" }
        );
        res.json({ token });
    }
);
```
Or, if the endpoint is not needed, delete it entirely.

**False Positive Assessment:** Route is registered unconditionally; handler runs on every request with no pre-gate. CONFIRMED.

---

### AG-H-01: Unauthenticated `/admin/flush-cache`

**Severity:** HIGH — **CWE-306** — **File:** `src/routes/admin.ts:7-11`

The handler is currently a stub but the route shape is already dangerous. **Remediation:** mount `adminRoutes` behind an authenticated middleware or remove until wired.

---

### AG-H-02: Unauthenticated `/score` proxy

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Category | AuthZ / Open Proxy |
| CWE | CWE-441 — Unintended Proxy or Intermediary |

**Description:** `POST /score` forwards the client's JSON body verbatim to `${API_UPSTREAM}/predict` with no caller authentication and no schema validation.

**File:** `src/server.ts:28-31`

**Code Evidence:**
```ts
app.post("/score", async (req, res) => {
    const result = await forwardToFraudScoring(req.body);
    res.json(result);
});
```

**Attack Scenario:** See cross-repo Chain B — anonymous callers reach the fraud model via the gateway and poison the scorer with user-supplied `velocity_24h` / `count_last_1h`.

**Remediation:** Require `Authorization: Bearer …` with a verified JWT; validate the request body against a schema before forwarding.

---

### AG-H-03: `jwt.verify` never called anywhere

**Severity:** HIGH — **CWE-287** — **Files:** `src/server.ts`, `src/routes/admin.ts`

`jsonwebtoken` is imported but only `jwt.sign` is used. The gateway takes no tokens on input. **Remediation:** Add `jwt.verify(token, secret, { algorithms: ["HS256"] })` in a middleware applied before every authenticated route, and apply it to `/admin/*` and `/score`.

---

### AG-H-04: Hardcoded JWT fallback secret

**Severity:** HIGH — **CWE-798** — **File:** `src/routes/admin.ts:15`

```ts
const secret = process.env.JWT_SECRET ?? "fallback-secret-for-dev";
```

**Remediation:** Fail-closed:
```ts
const secret = process.env.JWT_SECRET;
if (!secret) {
    throw new Error("JWT_SECRET must be set at startup");
}
```

---

### AG-H-05: Slack webhook URL committed

**Severity:** HIGH — **CWE-798** — **File:** `config/.env.staging:6`

`SLACK_WEBHOOK=https://hooks.slack.com/services/…` — Slack webhook URLs are bearer credentials. **Remediation:** Revoke and regenerate the webhook; move into secrets manager; never commit webhook URLs.

---

### AG-H-06: Final container image runs as root

**Severity:** HIGH — **CWE-250** — **File:** `Dockerfile:6-13`

No `USER` directive in the `node:20-slim` stage. Business-logic §2 carveout covers only the builder stage. **Remediation:**
```dockerfile
RUN useradd -u 10001 app && chown -R app /app
USER app
```

---

### AG-H-07: npm dependencies unpinned

**Severity:** HIGH — **CWE-1357** — **File:** `package.json:11-21`

All deps use `^` ranges and no `package-lock.json` is committed. **Remediation:** Generate and commit `package-lock.json`; use `npm ci` (see AG-M-03); set `"engines": { "npm": "≥ 10" }` and `save-exact = true` in `.npmrc`.

---

## Section 3 — Medium & Low Findings (Condensed)

### AG-M-01: No algorithm/expiry on `jwt.sign` — MEDIUM
**CWE-1188 + CWE-613** | `src/routes/admin.ts:16`
**Remediation:** `jwt.sign(payload, secret, { algorithm: "HS256", expiresIn: "15m" })`; pair with a `jwt.verify(..., { algorithms: ["HS256"] })` allowlist.

### AG-M-02: Secrets baked into image layers — MEDIUM
**CWE-538** | `Dockerfile:9`
**Remediation:** add `.dockerignore` for `config/.env.*`.

### AG-M-03: `npm install` used instead of `npm ci` — MEDIUM
**CWE-1357** | `Dockerfile:4`
**Remediation:** replace with `RUN npm ci --omit=dev`; requires a committed lockfile.

### AG-M-04: No timeout/retry/circuit-breaker on upstream fetch — MEDIUM
**CWE-730** | `src/server.ts:17-26`
**Remediation:** wrap `fetch` with `AbortController` (5 s), a retry policy, and a circuit breaker (`opossum` or similar).

### AG-L-01: Email PII carried in JWT payload — LOW
**CWE-359** | `src/routes/admin.ts:16`
**Remediation:** use an opaque user id as `sub`; keep email in a server-side mapping.

### AG-L-02: `dotenv` listed but never imported — LOW
**CWE-1104** | `package.json:15`
**Remediation:** remove from `dependencies`.

### AG-L-03: Unhandled promise rejection on `/score` — LOW
**CWE-754** | `src/server.ts:28-31`
**Remediation:** wrap in `try/catch` and `next(err)`; enable Express 5 async handler semantics or use `express-async-errors`.

---

## Section 4 — Remediation Roadmap

### Priority 1 — Immediate (48 hours)

| Action | Findings | Owner |
|--------|----------|-------|
| Delete `process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"` at server.ts:10 | X-06 (cross-repo) | Dev |
| Gate or delete `/admin/issue-token`; require admin auth, stop granting hardcoded role | AG-C-01 | Dev + Security |
| Rotate `JWT_SECRET`, remove fallback literal, revoke Slack webhook | AG-H-04, AG-H-05, X-01 | Security |

### Priority 2 — Urgent (2 weeks)

| Action | Findings | Owner |
|--------|----------|-------|
| Add authentication middleware to all `/admin/*` and `/score` routes; implement `jwt.verify` | AG-H-01, AG-H-02, AG-H-03 | Dev |
| Add `USER app` to final Dockerfile stage | AG-H-06 | DevOps |
| Pin dependencies with lockfile + `npm ci`; add `.dockerignore` | AG-H-07, AG-M-02, AG-M-03 | DevOps |

### Priority 3 — Important (30 days)

| Action | Findings | Owner |
|--------|----------|-------|
| Specify algorithm + expiry on all `jwt.sign` calls; opaque `sub` | AG-M-01, AG-L-01 | Dev |
| Add timeout / retry / circuit breaker on upstream fetch | AG-M-04 | Dev |
| Add async-error middleware | AG-L-03 | Dev |

### Priority 4 — Strategic (90 days)

| Action | Findings | Owner |
|--------|----------|-------|
| Introduce service mesh with mTLS and an IdP-issued token boundary | X-02 | Architecture |
| Add CI build + test step for auth-gateway (currently unbuilt) | (S06-AG-01) | DevOps |

---

## Section 5 — Methodology & Scope

Same pipeline as fraud-scoring report. Per-scan raw findings under `results/scans/auth-gateway-scan-0N-*.md`.

**Limitations:** No DAST; `jsonwebtoken`'s default algorithm behavior is assumed per library docs, not verified at runtime.

---

## Appendix A — Secrets Inventory

| Secret | Type | Location(s) | Rotation Status |
|--------|------|-------------|-----------------|
| `Welcome2ACI-shared-2026` | JWT secret (shared with fraud-scoring) | `config/.env.staging:3` | Rotate + split per-service |
| `https://hooks.slack.com/services/T0XXXXXX/B0YYYYYY/zzzz…` | Slack webhook | `config/.env.staging:6` | Revoke + regenerate |
| `fallback-secret-for-dev` | Hardcoded JWT fallback | `src/routes/admin.ts:15` | Delete code path |

## Appendix B — File Inventory

| File | Lines | Risk Level | Notes |
|------|------:|-----------|-------|
| `src/server.ts` | 33 | **CRITICAL** | Open proxy + TLS-off at module load |
| `src/routes/admin.ts` | 18 | **CRITICAL** | Unauth admin-token mint |
| `config/.env.staging` | 8 | **HIGH** | Shared JWT secret + Slack webhook |
| `Dockerfile` | 13 | **HIGH** | Root user, `npm install`, tag-pinned |
| `package.json` | 22 | **HIGH** | Unpinned deps, no lockfile |
