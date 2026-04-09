---
name: docker-image-audit
description: Audit Docker images and Dockerfiles for security vulnerabilities, bloat, and best-practice violations using hadolint, Trivy, and Grype. Produces a structured severity report with actionable fixes. Use this skill whenever the user wants to check a Docker image for security issues, scan a container for vulnerabilities, audit a Dockerfile, harden a Docker image, reduce image size, minimize attack surface, check for CVEs in a container, or says things like "is this Dockerfile secure?", "scan my image", "check my container for vulnerabilities", "how can I make this image smaller?", "audit my Docker setup", or "harden this container". Also trigger when the user has just created or modified a Dockerfile and wants validation before shipping it.
user-invocable: true
---

# Docker Image Audit

Comprehensive security and best-practice audit for Docker images and Dockerfiles. This skill combines three complementary tools — hadolint for static Dockerfile analysis, Trivy for vulnerability scanning, and Grype for a second-opinion vulnerability scan — then synthesizes findings into a single structured report with severity levels and concrete fixes.

Why three tools instead of one: hadolint catches Dockerfile anti-patterns before you build (wrong base image, missing `--no-cache`, running as root). Trivy and Grype both scan the built image for known CVEs, but they use different vulnerability databases and detection heuristics — running both catches things either alone would miss and gives you higher confidence when both agree an image is clean.

## Prerequisites

The following tools must be available. If any are missing, tell the user how to install them before proceeding.

| Tool | Install | Purpose |
|------|---------|---------|
| **hadolint** | `brew install hadolint` or [GitHub releases](https://github.com/hadolint/hadolint/releases) | Static analysis of Dockerfiles |
| **trivy** | `brew install trivy` or [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | Vulnerability scanning of images and filesystems |
| **grype** | `brew install grype` or [anchore/grype](https://github.com/anchore/grype) | Vulnerability scanning with Anchore's database |

Check availability:
```bash
command -v hadolint && command -v trivy && command -v grype
```

## Workflow

### Step 1: Identify the Audit Target

Determine what the user wants audited:

- **Dockerfile only** — static analysis with hadolint (no built image needed)
- **Built image** — full scan with Trivy + Grype (image must exist locally or in a registry)
- **Both** — Dockerfile analysis + image scan (the default when both are available)

If the user points to a Dockerfile but no built image exists, offer to build it first:
```
I found a Dockerfile but no built image. Want me to build it so I can run vulnerability scans?
If you only want static Dockerfile analysis, I can do that without building.
```

### Step 2: Run Hadolint (Static Dockerfile Analysis)

Run hadolint on the Dockerfile with JSON output for structured parsing:

```bash
hadolint --format json Dockerfile
```

Hadolint checks for:
- **Base image issues** — using `latest` tag, unpinned versions, deprecated images
- **Security anti-patterns** — running as root, using `ADD` instead of `COPY` for URLs, storing secrets
- **Efficiency problems** — not combining `RUN` commands, missing `--no-cache` on `apk add`, not cleaning apt cache
- **Shellcheck integration** — linting shell commands inside `RUN` instructions

Each finding has a rule ID (e.g., `DL3006`, `SC2086`) and severity level.

### Step 3: Run Trivy (Vulnerability Scan)

Scan the image with Trivy, outputting JSON for structured parsing:

```bash
trivy image --format json --severity CRITICAL,HIGH,MEDIUM,LOW --output trivy-report.json <image-name>
```

Also run a filesystem scan on the project directory to catch vulnerabilities in application dependencies that might not appear in the image scan:

```bash
trivy fs --format json --severity CRITICAL,HIGH,MEDIUM,LOW --output trivy-fs-report.json .
```

Trivy checks:
- **OS package vulnerabilities** — CVEs in packages installed in the image
- **Application dependency vulnerabilities** — CVEs in npm, pip, Go, Maven, etc. dependencies
- **Misconfigurations** — if `--scanners misconfig` is added
- **Secret detection** — if `--scanners secret` is added

### Step 4: Run Grype (Second-Opinion Vulnerability Scan)

Scan the same image with Grype for cross-validation:

```bash
grype <image-name> -o json > grype-report.json
```

Grype uses Anchore's vulnerability database, which sometimes catches CVEs that Trivy misses (and vice versa). The comparison between the two is where confidence comes from.

### Step 5: Analyze Image Size and Layer Efficiency

Inspect the image to identify bloat:

```bash
docker image inspect <image-name> --format '{{.Size}}'
docker history <image-name> --no-trunc --format '{{.Size}}\t{{.CreatedBy}}'
```

Look for:
- **Large layers** — any single layer over 100MB deserves scrutiny
- **Build artifacts in the final image** — compilers, dev headers, test frameworks
- **Package manager caches** — apt lists, pip cache, npm cache
- **Unnecessary OS packages** — anything not required at runtime
- **Multiple `COPY . .` instructions** — each creates a new layer with the full source
- **Base image size** — compare against distroless or slim alternatives

### Step 6: Synthesize the Report

Combine all findings into a single structured report. Write the report to a file (not chat) at a location the user can easily find — default to `docker-audit-report.md` in the project root.

#### Report Structure

```markdown
# Docker Image Audit Report

**Image**: <image-name-or-dockerfile-path>
**Date**: <date>
**Tools**: hadolint <version>, Trivy <version>, Grype <version>

## Executive Summary

| Category | Critical | High | Medium | Low | Info |
|----------|----------|------|--------|-----|------|
| Dockerfile issues (hadolint) | X | X | X | X | X |
| OS vulnerabilities (Trivy) | X | X | X | X | - |
| OS vulnerabilities (Grype) | X | X | X | X | - |
| App dependency vulnerabilities | X | X | X | X | - |
| Image size & efficiency | - | X | X | X | - |
| **Total** | **X** | **X** | **X** | **X** | **X** |

**Image size**: XXX MB
**Recommended target**: XXX MB (using <recommended-base>)
**Non-root user**: Yes/No
**Health check**: Present/Missing

## Critical and High Findings

List each CRITICAL and HIGH finding with:

### [SEVERITY] Finding title
- **Source**: hadolint/Trivy/Grype
- **Rule/CVE**: DL3006 / CVE-2024-XXXXX
- **Component**: package name and version
- **Description**: What the vulnerability or issue is
- **Fix**: Specific action to take
  - If a package upgrade fixes it: show the version to upgrade to
  - If a Dockerfile change fixes it: show the before/after
  - If no fix is available: note this and suggest mitigation

## Medium and Low Findings

Same structure, but these can be grouped by category for readability.

## Image Size Analysis

### Current Layer Breakdown
| Size | Layer |
|------|-------|
| XX MB | RUN apt-get install ... |
| XX MB | COPY . . |
| ... | ... |

### Size Reduction Recommendations
1. Recommendation with estimated size savings
2. ...

## Cross-Validation Summary

Findings detected by both Trivy and Grype have high confidence.
Findings detected by only one scanner should be investigated but may be false positives.

| CVE | Trivy | Grype | Confidence |
|-----|-------|-------|------------|
| CVE-2024-XXXXX | Yes | Yes | High |
| CVE-2024-YYYYY | Yes | No | Medium |

## Recommended Dockerfile Changes

If the audit identified Dockerfile improvements, provide the specific changes as a unified diff or before/after blocks. Group changes by priority:

1. **Security fixes** (non-root user, secret removal, base image update)
2. **Vulnerability remediation** (package upgrades, base image swap)
3. **Size reduction** (multi-stage build, cache cleanup, distroless migration)
4. **Best practices** (layer ordering, label addition, health checks)
```

### Severity Classification

Map findings to consistent severity levels across all three tools:

| Severity | Criteria | Action Required |
|----------|----------|-----------------|
| **CRITICAL** | Actively exploited CVE, remote code execution, exposed secrets | Fix immediately — do not ship |
| **HIGH** | Known CVE with public exploit, running as root, no user namespace | Fix before production deployment |
| **MEDIUM** | Known CVE without public exploit, missing health check, unpinned base | Fix in next iteration |
| **LOW** | Informational CVE, minor best-practice deviation | Fix when convenient |
| **INFO** | Hadolint style suggestions, optimization opportunities | Consider adopting |

### Handling Disagreements Between Scanners

When Trivy and Grype disagree:
- **Both flag it**: High confidence — include as-is
- **Only one flags it**: Medium confidence — include it but note which scanner found it and that the other didn't. The user should investigate.
- **Neither flags it but hadolint warns**: The issue is in the Dockerfile structure, not a CVE — include under Dockerfile findings

## Quick Audit Mode

If the user just wants a fast pass (e.g., "quick check on this Dockerfile"), run only hadolint and report the top findings conversationally instead of generating the full report. Always include:

- Security issues (running as root, exposed secrets, missing USER)
- Cache efficiency problems (COPY ordering)
- Base image recommendations — if a smaller variant exists (e.g., alpine, slim, chiseled, distroless), suggest the switch with estimated size savings
- Missing .dockerignore

Mention that a full image scan is available if they want deeper analysis.
