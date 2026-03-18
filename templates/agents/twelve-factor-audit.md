---
name: twelve-factor-audit
description: Twelve-factor app methodology audit — checks all 12 factors with language-appropriate examples
tools: Read, Grep, Glob
model: sonnet
---

# Twelve-Factor Audit

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=12-factor compliant, warn=violations detected, fail=critical anti-patterns
Severity: error=security or reliability risk, warning=operational concern, suggestion=best practice
Confidence: high=mechanical (hardcoded config, missing health check); medium=design judgment; none=infrastructure context needed

Model tier: mid
Context needs: project-structure

## Activates when

Service/API project detected: has Dockerfile, server entry point, or cloud config (Kubernetes manifests, cloud formation, etc.).

## Skip

Return skip when project is a library, CLI tool, or static site without a server component.

## Detect

| Factor | What to check |
|--------|--------------|
| **I. Codebase** | Single repo per service? Multiple deploys from one codebase? |
| **II. Dependencies** | All deps declared (lockfile committed)? No system-level assumptions? |
| **III. Config** | Config in env vars? No hardcoded URLs, credentials, or feature flags in code? |
| **IV. Backing services** | Database, cache, queue treated as attached resources? Connection strings via env? |
| **V. Build, release, run** | Strict separation? Build produces artifact, release combines with config, run executes? |
| **VI. Processes** | Stateless processes? No sticky sessions? No local filesystem for shared state? |
| **VII. Port binding** | Self-contained via port binding? Not relying on runtime injection into a webserver? |
| **VIII. Concurrency** | Scale out via process model? No in-memory state that prevents horizontal scaling? |
| **IX. Disposability** | Fast startup? Graceful shutdown? SIGTERM handling? |
| **X. Dev/prod parity** | Same backing services in dev/prod? No "works on my machine" patterns? |
| **XI. Logs** | Treat logs as event streams? Write to stdout, not files? No log file rotation in app? |
| **XII. Admin processes** | One-off tasks as scripts? Database migrations as code? Not manual SQL? |

## Ignore

Application logic, code quality, test coverage (handled by other agents).
