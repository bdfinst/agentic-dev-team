# Docker Audit Report Template

Use this structure when writing the report file. Replace placeholders with actual findings.

```markdown
# Docker Image Audit Report

**Image**: <image-name-or-dockerfile-path>
**Date**: <date>
**Tools**: hadolint <version>, Trivy <version>, Grype <version>

## Executive Summary

| Category | Critical | High | Medium | Low | Info |
|----------|----------|------|--------|-----|------|
| Dockerfile issues (hadolint) | X | X | X | X | X |
| Structural issues (manual) | X | X | X | X | - |
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

### [SEVERITY] Finding title
- **Source**: hadolint/Trivy/Grype/structural
- **Rule/CVE**: DL3006 / CVE-2024-XXXXX
- **Component**: package name and version
- **Description**: What the vulnerability or issue is
- **Fix**: Specific action to take (show before/after for Dockerfile changes, version to upgrade to, or mitigation if no fix available)

## Medium and Low Findings

Same structure, grouped by category for readability.

## Image Size Analysis

### Current Layer Breakdown
| Size | Layer |
|------|-------|
| XX MB | RUN apt-get install ... |
| XX MB | COPY . . |

### Size Reduction Recommendations
1. Recommendation with estimated size savings

## Cross-Validation Summary

Findings detected by both Trivy and Grype have high confidence.
Findings detected by only one scanner should be investigated but may be false positives.

| CVE | Trivy | Grype | Confidence |
|-----|-------|-------|------------|
| CVE-2024-XXXXX | Yes | Yes | High |
| CVE-2024-YYYYY | Yes | No | Medium |

## Recommended Dockerfile Changes

Group changes by priority:

1. **Separation of concerns** (move CI/CD steps out of Dockerfile)
2. **Security fixes** (secrets to BuildKit mounts, non-root user, TLS, base image)
3. **Vulnerability remediation** (package upgrades, base image swap)
4. **Build correctness** (Debug/Release mismatch, remove post-build workarounds)
5. **Cache & size optimization** (COPY ordering, .dockerignore, layer consolidation, distroless)
6. **Best practices** (HEALTHCHECK, labels, WORKDIR, dead stage cleanup)
```
