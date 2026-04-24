# OWASP Detection Patterns

Reference file for the security-review agent. Read this before starting
analysis to apply language-specific detection patterns.

When a pattern matches, the agent emits a finding with the row's
**Category** identifier. Category identifiers follow the regex
`^A[0-9]{2}\.[a-z0-9-]+$` and are canonical — see
`plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml` for
the full list mapped to rule_ids.

> Scope note: only **judgment-only** patterns carry a Category column in
> this file today. Pattern-visible classes (those detected by semgrep
> rulesets) will be removed from this reference in Item 3b once the
> rule set lands. Pattern-visible rows intentionally remain unannotated
> pending that removal.

## A01: Broken Access Control

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Missing auth middleware | JS/TS | Route handlers without `authenticate`, `auth`, `protect` middleware | `A01.missing-auth-middleware` |
| Missing [Authorize] | C# | Controllers/actions without `[Authorize]` or `[AllowAnonymous]` | `A01.missing-authorize-csharp` |
| Missing @PreAuthorize | Java | Controllers without `@PreAuthorize`, `@Secured`, or `@RolesAllowed` | `A01.missing-auth-middleware` |
| IDOR | All | Route params used directly as DB keys without ownership check | `A01.idor` |
| Path traversal | All | `Path.Combine`, `path.join`, `Paths.get` with user-controlled input | |

## A02: Cryptographic Failures

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Weak hashing | All | `MD5`, `SHA1` used for passwords or tokens |
| Hardcoded keys | All | `(?i)(api[_-]?key\|secret\|password\|token)\s*[:=]\s*['"][^'"]{8,}` |
| No TLS validation | C# | `ServerCertificateValidationCallback` returning true |
| Insecure random | JS/TS | `Math.random()` for tokens/secrets |
| Insecure random | C# | `new Random()` for tokens/secrets (should use `RandomNumberGenerator`) |
| Insecure random | Java | `java.util.Random` for tokens/secrets (should use `SecureRandom`) |

## A03: Injection

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| SQL injection | JS/TS | Template literals or string concat in `query(`, `execute(` |
| SQL injection | C# | String interpolation/concat in `SqlCommand`, `ExecuteReader`, `FromSqlRaw` |
| SQL injection | Java | String concat in `createQuery`, `prepareStatement` without `?` |
| XSS | JS/TS | `innerHTML`, `dangerouslySetInnerHTML`, `document.write` with variables |
| XSS | C# | `Html.Raw()` with user input, missing `[ValidateAntiForgeryToken]` |
| Command injection | All | User input in `exec`, `spawn`, `Process.Start`, `Runtime.exec` |
| Template injection | All | User input in template engine render calls |

## A04: Insecure Design

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| No rate limiting | All | Auth endpoints without rate limit middleware | `A04.no-rate-limiting` |
| No brute force protection | All | Login handlers without lockout/throttle | `A04.no-brute-force-protection` |
| Missing CSRF | C# | POST/PUT handlers without `[ValidateAntiForgeryToken]` | |

## A05: Security Misconfiguration

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Debug in prod | JS/TS | `DEBUG=true`, `NODE_ENV` not checked | |
| Debug in prod | C# | `<DebugType>full</DebugType>` in Release config | |
| Permissive CORS | All | `Access-Control-Allow-Origin: *`, `AllowAnyOrigin()` | |
| Missing security headers | All | No CSP, HSTS, X-Frame-Options, X-Content-Type-Options | |
| Default credentials | All | `admin/admin`, `root/root`, `password` in config | |
| Verbose errors | All | Stack traces in HTTP responses, `app.UseDeveloperExceptionPage()` in prod | `A05.verbose-errors-prod` |

## A06: Vulnerable Components

| Detection method | Language |
|-----------------|----------|
| `npm audit` | JS/TS |
| `dotnet list package --vulnerable` | C# |
| `mvn dependency-check:check` or OWASP plugin | Java |

## A07: Authentication Failures

| Pattern | Language | Grep Signal | Category |
|---------|----------|-------------|----------|
| Weak password hashing | All | `bcrypt` cost < 10, plain MD5/SHA for passwords | |
| JWT algorithm confusion | All | `algorithms: ['none']`, no algorithm validation | |
| JWT no expiry | All | JWT creation without `exp` claim | `A07.jwt-no-exp` |
| Session fixation | All | Session ID not regenerated after login | `A07.session-fixation` |
| Insecure cookie | All | Missing `Secure`, `HttpOnly`, `SameSite` flags | |

## A08: Data Integrity Failures

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Unsafe deserialization | C# | `BinaryFormatter`, `TypeNameHandling.All` |
| Unsafe deserialization | Java | `ObjectInputStream` with untrusted input |
| Unsafe deserialization | JS/TS | `eval()`, `Function()` with user input |

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
