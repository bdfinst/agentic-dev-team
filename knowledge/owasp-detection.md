# OWASP Detection Patterns

Reference file for the security-review agent. Read this before starting
analysis to apply language-specific detection patterns.

## A01: Broken Access Control

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Missing auth middleware | JS/TS | Route handlers without `authenticate`, `auth`, `protect` middleware |
| Missing [Authorize] | C# | Controllers/actions without `[Authorize]` or `[AllowAnonymous]` |
| Missing @PreAuthorize | Java | Controllers without `@PreAuthorize`, `@Secured`, or `@RolesAllowed` |
| IDOR | All | Route params used directly as DB keys without ownership check |
| Path traversal | All | `Path.Combine`, `path.join`, `Paths.get` with user-controlled input |

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

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| No rate limiting | All | Auth endpoints without rate limit middleware |
| No brute force protection | All | Login handlers without lockout/throttle |
| Missing CSRF | C# | POST/PUT handlers without `[ValidateAntiForgeryToken]` |

## A05: Security Misconfiguration

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Debug in prod | JS/TS | `DEBUG=true`, `NODE_ENV` not checked |
| Debug in prod | C# | `<DebugType>full</DebugType>` in Release config |
| Permissive CORS | All | `Access-Control-Allow-Origin: *`, `AllowAnyOrigin()` |
| Missing security headers | All | No CSP, HSTS, X-Frame-Options, X-Content-Type-Options |
| Default credentials | All | `admin/admin`, `root/root`, `password` in config |
| Verbose errors | All | Stack traces in HTTP responses, `app.UseDeveloperExceptionPage()` in prod |

## A06: Vulnerable Components

| Detection method | Language |
|-----------------|----------|
| `npm audit` | JS/TS |
| `dotnet list package --vulnerable` | C# |
| `mvn dependency-check:check` or OWASP plugin | Java |

## A07: Authentication Failures

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Weak password hashing | All | `bcrypt` cost < 10, plain MD5/SHA for passwords |
| JWT algorithm confusion | All | `algorithms: ['none']`, no algorithm validation |
| JWT no expiry | All | JWT creation without `exp` claim |
| Session fixation | All | Session ID not regenerated after login |
| Insecure cookie | All | Missing `Secure`, `HttpOnly`, `SameSite` flags |

## A08: Data Integrity Failures

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| Unsafe deserialization | C# | `BinaryFormatter`, `TypeNameHandling.All` |
| Unsafe deserialization | Java | `ObjectInputStream` with untrusted input |
| Unsafe deserialization | JS/TS | `eval()`, `Function()` with user input |

## A09: Logging & Monitoring Failures

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| PII in logs | All | Logging `password`, `ssn`, `creditCard`, `token` fields |
| No auth event logging | All | Login/logout/failure handlers without log statements |
| Sensitive data in errors | All | Exception messages containing connection strings, keys |

## A10: SSRF

| Pattern | Language | Grep Signal |
|---------|----------|-------------|
| User-controlled URLs | All | User input in `fetch()`, `HttpClient`, `URL()` without allowlist |
| Internal network access | All | Requests to `localhost`, `127.0.0.1`, `169.254.169.254` |
