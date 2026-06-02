---
name: docker-image-audit
description: Audit Docker images and Dockerfiles for security vulnerabilities, bloat, and best-practice violations using hadolint, Trivy, and Grype. Produces a structured severity report with actionable fixes. Use this skill whenever the user wants to check a Docker image for security issues, scan a container for vulnerabilities, audit a Dockerfile, harden a Docker image, reduce image size, minimize attack surface, check for CVEs in a container, or says things like "is this Dockerfile secure?", "scan my image", "check my container for vulnerabilities", "how can I make this image smaller?", "audit my Docker setup", or "harden this container". Also trigger when the user has just created or modified a Dockerfile and wants validation before shipping it.
user-invocable: true
---

# Docker Image Audit

Audit Dockerfiles and container images using three complementary tools — hadolint (static Dockerfile linting), Trivy (CVE scanning), and Grype (second-opinion CVE scanning) — plus manual structural analysis for architectural issues the tools miss. Synthesize all findings into a single severity-ranked report with concrete fixes.

## Prerequisites

```bash
command -v hadolint && command -v trivy && command -v grype
```

| Tool | Quick install (macOS) | Purpose |
|------|----------------------|---------|
| **hadolint** | `brew install hadolint` | Static Dockerfile analysis |
| **trivy** | `brew install trivy` | Vulnerability scanning |
| **grype** | `brew install grype` | Second-opinion CVE scanning |

If any tool is missing, read `references/install-guide.md` for multi-platform install instructions. The skill degrades gracefully — hadolint alone covers static analysis; Trivy + Grype require a built image. **If no tools are installed, still run the structural analysis (Step 2b). A tool-free audit is better than no audit.**

## Workflow

### Step 1: Identify the Target

- **Dockerfile only** — hadolint + structural analysis (no built image needed)
- **Built image** — Trivy + Grype (image must exist locally or in a registry)
- **Both** — all steps (default when both are available)

If the user points to a Dockerfile but no built image exists, offer to build it or proceed with Dockerfile-only analysis.

### Step 2: Hadolint

```bash
hadolint --format json Dockerfile
```

Catches base image issues (`:latest` tag, unpinned versions), security anti-patterns (`ADD` vs `COPY`, running as root), efficiency problems (missing `--no-cache`, uncleaned apt cache), and shell issues in `RUN` instructions via integrated ShellCheck. Note: hadolint flags `:latest` (`DL3007`) but not other unpinned tags like `:10.0` without a digest — call those out in Step 2b if the base image lacks a specific patch version or SHA digest.

### Step 2b: Structural Analysis

Hadolint catches per-instruction issues but misses architectural problems. Read the Dockerfile and check for these patterns — they are **not optional** and often represent the most impactful findings.

| Check | What to look for | Severity |
|-------|-----------------|----------|
| **"God Dockerfile"** | CI/CD baked into the build: SonarQube, Black Duck, Snyk, Helm packaging, `curl` uploads to Nexus/Artifactory, `npm publish`, `git clone`. The Dockerfile should produce a runnable image — everything else belongs in CI pipeline definitions. | **HIGH** |
| **Secrets in ARGs** | `ARG` names matching `*_TOKEN`, `*_SECRET`, `*_KEY`, `*_PASSWORD`, `*_CREDENTIALS`. ARGs persist in image layer metadata (`docker history --no-trunc`). Fix: use `RUN --mount=type=secret`. If secrets are only for CI stages, the better fix is moving those stages out of the Dockerfile. | **HIGH** |
| **Missing .dockerignore + broad COPY** | `COPY . .` without a `.dockerignore` sends `.git/`, `node_modules/`, `bin/`, `obj/`, IDE config, and local secrets into the build context. | **HIGH** |
| **Config mismatch** | Building/testing in Debug but publishing in Release (or vice versa). Tests should validate the exact bits that ship. Also flag post-build `jq`/`sed`/`awk` patching of output files — suggests misconfigured build flags. | **MEDIUM** |
| **Redundant COPY** | Broad `COPY . .` followed by selective copies (redundant); same files re-copied across stages; `COPY . .` before `RUN <restore>` busting the dependency cache. Fix: copy manifests first (`*.csproj`, `package-lock.json`, `go.sum`), restore, then copy source. | **MEDIUM** |
| **TLS verification disabled** | `--insecure-skip-tls-verify`, `curl -k`, `NODE_TLS_REJECT_UNAUTHORIZED=0`, `GIT_SSL_NO_VERIFY=true`. Vulnerable to MITM. Fix: configure proper CA certs. | **MEDIUM** |
| **Missing HEALTHCHECK** | Final stage has no `HEALTHCHECK` instruction. Orchestrators can't detect unhealthy containers. | **MEDIUM** |
| **Baked-in configuration** | Hardcoded environment-specific URLs, API keys, database connection strings, or service endpoints in `ENV` or config files copied into the image. These should be injected at runtime via environment variables, orchestrator secrets, or ConfigMaps. | **MEDIUM** |
| **Swiss Army Knife image** | Build tools, compilers, test runners, or dev dependencies present in the final production stage. Check the final `FROM` base (full SDK vs. runtime/slim/distroless) and look for `COPY --from=build` that pulls more than just the application binaries. Fix: multi-stage build where the final stage contains only the runtime and published output. | **MEDIUM** |
| **Stateful container** | Writing logs, uploads, temp files, or session data to the container's writable layer (`VOLUME` pointing to local paths, `RUN mkdir /data`). Containers should be ephemeral — use external volumes, object storage, or centralized logging. Flag `VOLUME` instructions that suggest local state. | **MEDIUM** |
| **Dead-end stages** | Stages copying to `scratch` that aren't targeted, or stages whose output (reports, charts) is never referenced by the final stage. Wastes build time. | **LOW** |
| **UID/GID mismatch** | `--chown=<uid>` doesn't match the `USER` in the same stage. Verify the UID maps to the expected user in the base image. | **LOW** |
| **Language-specific anti-patterns** | **Python**: `pip install` without `--no-cache-dir`; unpinned versions. **Node**: `npm install` instead of `npm ci`; missing `NODE_ENV=production`. **Go**: missing `CGO_ENABLED=0` for scratch/distroless. **.NET**: missing `--locked-mode` on restore; copying `bin/`/`obj/`. **Java**: full JDK as runtime base when JRE suffices. **Multi-platform**: missing `--platform` in `FROM`. | **MEDIUM** |

### Step 3: Trivy

Run if a built image or project filesystem is available:

```bash
trivy image --format json --severity CRITICAL,HIGH,MEDIUM,LOW --output trivy-report.json <image>
trivy fs --format json --severity CRITICAL,HIGH,MEDIUM,LOW --output trivy-fs-report.json .
```

The image scan catches OS package CVEs; the filesystem scan catches application dependency CVEs (npm, pip, Go, Maven, etc.). Also supports `--scanners misconfig,secret` for bonus coverage.

### Step 4: Grype

```bash
grype <image> -o json > grype-report.json
```

Cross-validates against Anchore's vulnerability database. When both Trivy and Grype flag a CVE, confidence is high. When only one flags it, note the disagreement — the user should investigate.

### Step 5: Image Size & Layers

```bash
docker image inspect <image> --format '{{.Size}}'
docker history <image> --no-trunc --format '{{.Size}}\t{{.CreatedBy}}'
```

Flag layers over 100MB, build artifacts in the final image (compilers, dev headers), package manager caches, and opportunities to switch to distroless/slim bases.

### Step 6: Write the Report

Write findings to `docker-audit-report.md` in the project root (not chat). Use the template in `references/report-template.md` for structure. Every finding needs a source, severity, description, and concrete fix.

## Severity Classification

| Severity | Criteria |
|----------|----------|
| **CRITICAL** | Actively exploited CVE, RCE, exposed secrets in final image |
| **HIGH** | Known CVE with public exploit, secrets in ARGs, "God Dockerfile", missing .dockerignore + broad COPY, root in final stage |
| **MEDIUM** | Known CVE without public exploit, missing HEALTHCHECK, unpinned base, config mismatch, redundant COPY, TLS disabled, baked-in configuration, Swiss Army Knife image, stateful container patterns, language-specific anti-patterns |
| **LOW** | Informational CVE, dead-end stages, UID/GID mismatch, root in build-only stages |
| **INFO** | Style suggestions, layer consolidation opportunities |

## Quick Audit Mode

For fast passes (e.g., "quick check on this Dockerfile"), run Step 2 (hadolint) + Step 2b (structural analysis) and report findings conversationally — no report file. Skip Steps 3-5. Mention that a full image scan with Trivy + Grype is available for deeper CVE analysis.
