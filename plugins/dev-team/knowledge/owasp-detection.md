# OWASP Detection Patterns

Reference file for the security-review agent. Read this before starting
analysis to apply language-specific detection patterns.

When a pattern matches, the agent emits a finding with the row's
**Category** identifier. Category identifiers follow the regex
`^A[0-9]{2}\.[a-z0-9-]+$` and are canonical — see
`plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` for
the full list mapped to rule_ids.

> **Scope note (post Item 3b):** pattern-visible classes — those detected
> by semgrep rules with stable AST/regex shape and ≤10% FP rate per
> `docs/rules-vs-prompts-policy.md` — are NOT listed as agent detection
> patterns here. They appear as pointer stubs at the top of each OWASP
> section so the agent knows which classes the rule set covers and can
> still assess exploitability when a semgrep finding arrives in review
> context. Agent-detectable rows in this file are judgment classes only.

## A01: Broken Access Control

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Missing auth middleware | JS/TS | Route handlers without `authenticate`, `auth`, `protect` middleware | `A01.missing-auth-middleware` |
| Missing [Authorize] | C# | Controllers/actions without `[Authorize]` or `[AllowAnonymous]` | `A01.missing-authorize-csharp` |
| Missing @PreAuthorize | Java | Controllers without `@PreAuthorize`, `@Secured`, or `@RolesAllowed` | `A01.missing-auth-middleware` |
| IDOR | All | Route params used directly as DB keys without ownership check | `A01.idor` |
| Path traversal | All | `Path.Combine`, `path.join`, `Paths.get` with user-controlled input | |

## A02: Cryptographic Failures

**Pattern-visible classes detected by semgrep rules (agent assesses exploitability only):**

- Weak hashing (MD5/SHA1 used for passwords or tokens) — category `A02.weak-hashing-md5` → `semgrep.generic.weak-hash-md5` (also covered by `crypto-anti-patterns.md5-for-integrity`)
- Insecure random for tokens/secrets (`Math.random()`, `new Random()`, `java.util.Random`) — category `A02.insecure-random-js` for JS/TS (mapped to `semgrep.javascript.weak-random`); C# + Java variants covered by community rulesets

**Judgment classes detected by the agent:**

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Hardcoded keys | All | `(?i)(api[_-]?key\|secret\|password\|token)\s*[:=]\s*['"][^'"]{8,}` — note: `gitleaks` + `llm-safety.hardcoded-api-key` are authoritative for detection; agent's role here is exploitability assessment over tool findings, not primary detection |
| No TLS validation | C# | `ServerCertificateValidationCallback` returning true |

## A03: Injection

**Pattern-visible classes detected by semgrep rules (agent assesses exploitability only):**

- SQL injection via string concatenation (template literals in `query(`/`execute(`; `SqlCommand`/`ExecuteReader`/`FromSqlRaw`; `createQuery`/`prepareStatement` without `?`) — category `A03.sql-injection` → `semgrep.generic.sql-injection` (also covered by `datastore.sql.string-format-injection`)
- XSS via `innerHTML` / `dangerouslySetInnerHTML` / `document.write` / `Html.Raw()` with user input — category `A03.xss-innerhtml` → `semgrep.javascript.xss-innerhtml`

**Judgment classes detected by the agent:**

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Command injection | All | User input in `exec`, `spawn`, `Process.Start`, `Runtime.exec` |
| Template injection | All | User input in template engine render calls |

## A04: Insecure Design

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| No rate limiting | All | Auth endpoints without rate limit middleware | `A04.no-rate-limiting` |
| No brute force protection | All | Login handlers without lockout/throttle | `A04.no-brute-force-protection` |
| Missing CSRF | C# | POST/PUT handlers without `[ValidateAntiForgeryToken]` — framework-native; stays as agent per policy | |

## A05: Security Misconfiguration

**Pattern-visible classes detected by semgrep rules (agent assesses exploitability only):**

- Permissive CORS (`Access-Control-Allow-Origin: *`, `AllowAnyOrigin()`) — category `A05.cors-wildcard` → `semgrep.generic.cors-wildcard`

**Judgment classes detected by the agent:**

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Debug in prod | JS/TS | `DEBUG=true`, `NODE_ENV` not checked | |
| Debug in prod | C# | `<DebugType>full</DebugType>` in Release config | |
| Missing security headers | All | No CSP, HSTS, X-Frame-Options, X-Content-Type-Options | |
| Default credentials | All | `admin/admin`, `root/root`, `password` in config | |
| Verbose errors | All | Stack traces in HTTP responses, `app.UseDeveloperExceptionPage()` in prod | `A05.verbose-errors-prod` |

## A06: Vulnerable Components

| Detection method | Language |
|-----------------|----------|
| `npm audit` | JS/TS |
| `dotnet list package --vulnerable` | C# |
| `mvn dependency-check:check` or OWASP plugin | Java |

Authoritative tool: `trivy fs --scanners vuln`. Agent does not re-detect.

## A07: Authentication Failures

**Pattern-visible classes detected by semgrep rules (agent assesses exploitability only):**

- JWT algorithm confusion (`algorithms: ['none']`, no algorithm validation) — category `A07.jwt-alg-none` → `semgrep.generic.jwt-alg-none`

**Judgment classes detected by the agent:**

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Weak password hashing | All | `bcrypt` cost < 10 (distinct from A02 MD5/SHA hashing) | |
| JWT no expiry | All | JWT creation without `exp` claim | `A07.jwt-no-exp` |
| Session fixation | All | Session ID not regenerated after login | `A07.session-fixation` |
| Insecure cookie | All | Missing `Secure`, `HttpOnly`, `SameSite` flags | |

## A08: Data Integrity Failures

**Pattern-visible classes detected by semgrep rules (agent assesses exploitability only):**

- Unsafe deserialization via `BinaryFormatter` / `TypeNameHandling.All` (C#) — category `A08.binary-formatter` → `semgrep.csharp.binary-formatter`
- Unsafe deserialization via `ObjectInputStream` (Java) — category `A08.object-input-stream` → `semgrep.java.deserialization-object-input-stream`
- Unsafe deserialization via `eval()` / `Function()` with user input (JS/TS) — category `A08.js-eval` → `semgrep.javascript.eval-injection`

No judgment-only patterns in this category today. Agent's role is exploitability assessment over semgrep findings.

## A09: Logging & Monitoring Failures

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| PII in logs | All | Logging `password`, `ssn`, `creditCard`, `token` fields | `A09.pii-in-logs` |
| No auth event logging | All | Login/logout/failure handlers without log statements | `A09.no-auth-event-logging` |
| Sensitive data in errors | All | Exception messages containing connection strings, keys | |

## A10: SSRF

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| User-controlled URLs | All | User input in `fetch()`, `HttpClient`, `URL()` without allowlist |
| Internal network access | All | Requests to `localhost`, `127.0.0.1`, `169.254.169.254` |
