---
name: docker-image-create
description: Generate production-ready Dockerfiles from project source code. Detects language/framework automatically and produces multi-stage builds with minimal, distroless, or slim base images. Use this skill whenever the user wants to containerize an application, create a Dockerfile, dockerize a project, build a Docker image, or says things like "make this run in Docker", "create a container for this app", "I need a Dockerfile", "package this for deployment", or "containerize this service". Also trigger when the user has an existing Dockerfile and wants it rewritten for production use, or when they ask about Docker best practices for their project.
user-invocable: true
---

# Docker Image Creation

Generate production-ready Dockerfiles by analyzing the project's language, framework, and dependencies. The output is a multi-stage Dockerfile optimized for small image size, fast builds, and minimal attack surface — not a quick-and-dirty single-stage image that works but ships half a build toolchain into production.

## Why Multi-Stage and Distroless/Slim

A single-stage Dockerfile that installs build tools, compiles code, and runs the app in one image is simple but wasteful and insecure. Build tools (compilers, package managers, dev headers) bloat the image and expand the attack surface. Multi-stage builds solve this: one stage builds, a final stage copies only the runtime artifact into a minimal base.

- **Distroless images** (e.g., `gcr.io/distroless/static-debian12`) contain only the application and its runtime dependencies — no shell, no package manager, no OS utilities. This dramatically reduces CVE exposure.
- **Slim images** (e.g., `node:22-slim`, `python:3.12-slim`) are a pragmatic middle ground when the app needs OS-level libraries or a shell for debugging.

Default to distroless when possible. Fall back to slim when the runtime genuinely needs OS packages.

## Workflow

### Step 1: Detect the Project

Scan the project root to identify:

1. **Language and version** — look for version files, runtime configs, and source file extensions:
   - `package.json` (Node.js — check `engines.node` for version)
   - `go.mod` (Go — check `go` directive for version)
   - `requirements.txt`, `pyproject.toml`, `Pipfile` (Python — check `python_requires` or `.python-version`)
   - `pom.xml`, `build.gradle`, `build.gradle.kts` (Java/Kotlin — check for `sourceCompatibility`)
   - `*.csproj`, `*.fsproj` (C#/F# — check `TargetFramework`)
   - `mix.exs` (Elixir)
   - `Gemfile` (Ruby)

2. **Framework** — determines the build command and output structure:
   - Node.js: Next.js, Remix, Express, Fastify, NestJS, Astro, SvelteKit
   - Python: FastAPI, Flask, Django
   - Go: standard library net/http, Gin, Echo, Fiber
   - Java: Spring Boot, Quarkus, Micronaut
   - C#/.NET: ASP.NET Core, Blazor, gRPC, minimal APIs

3. **Package manager** — determines install commands:
   - Node.js: npm (`package-lock.json`), yarn (`yarn.lock`), pnpm (`pnpm-lock.yaml`), bun (`bun.lockb`)
   - Python: pip (`requirements.txt`), poetry (`poetry.lock`), pipenv (`Pipfile.lock`), uv (`uv.lock`)
   - Others: detected from build files

4. **Entry point** — how the app starts:
   - `package.json` `scripts.start`, `main` field
   - `Procfile`
   - `CMD` in any existing Dockerfile
   - Framework conventions (e.g., `main.go`, `app.py`, `Application.java`)

5. **Existing Docker artifacts** — check for `.dockerignore`, existing `Dockerfile`, `docker-compose.yml`

Present findings to the user:

```
Here's what I detected:

  Language:        Node.js 22
  Framework:       Next.js (standalone output)
  Package manager: pnpm
  Entry point:     next start (port 3000)
  Base image:      node:22-slim (final stage)
  Build image:     node:22 (build stage)

Want me to adjust anything before generating the Dockerfile?
```

### Step 2: Ask About Registry and Build Tools

Before generating, ask the user:

```
A couple of questions about your setup:

1. Container registry? (e.g., Docker Hub, ghcr.io, ECR, GCR, ACR)
   → This affects the FROM image paths and any login steps.

2. Build tool preference? (e.g., docker build, BuildKit, Podman, Buildah)
   → Default: BuildKit (DOCKER_BUILDKIT=1). This enables
     cache mounts, secret mounts, and parallel stage builds.

3. Need a .dockerignore file? (I'll generate one if missing)

4. Need a docker-compose.yml for local development?
```

Proceed with sensible defaults if the user says "just go with defaults" or similar.

### Step 3: Generate the Dockerfile

Follow these principles when generating:

#### Layer Ordering for Cache Efficiency

Order layers from least-frequently-changed to most-frequently-changed:
1. Base image selection
2. System dependencies (rarely change)
3. Dependency manifest copy + install (changes when deps change)
4. Source code copy (changes every build)
5. Build step
6. Final stage — copy only the built artifact

This ensures dependency installation is cached when only source code changes.

#### Dependency Installation

Copy only the dependency manifests first, install, then copy the rest of the source:

```dockerfile
# Good — cache-friendly
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build
```

Never `COPY . .` before installing dependencies — it busts the cache on every source change.

#### Multi-Stage Structure

```
Stage 1: "deps"    — Install dependencies (cached separately)
Stage 2: "build"   — Compile/bundle the application
Stage 3: "runtime" — Minimal base with only the built artifact
```

For interpreted languages (Python, Ruby, Node.js without a build step), two stages may suffice.

#### Base Image Selection

| Language | Build Stage | Runtime Stage |
|----------|-------------|---------------|
| Go | `golang:<version>` | `gcr.io/distroless/static-debian12` |
| Java | `eclipse-temurin:<version>` | `gcr.io/distroless/java21-debian12` |
| Node.js | `node:<version>` | `node:<version>-slim` or `gcr.io/distroless/nodejs22-debian12` |
| Python | `python:<version>` | `python:<version>-slim` |
| C#/.NET | `mcr.microsoft.com/dotnet/sdk:<version>` | `mcr.microsoft.com/dotnet/aspnet:<version>-alpine` |

Pin major.minor versions (e.g., `node:22.12`, not `node:latest`). Use digest pinning for high-security environments if the user requests it.

#### Security Defaults

- Run as a non-root user in the final stage (`USER nonroot` for distroless, create a user for slim bases)
- Don't copy `.env` files, secrets, or credentials into the image
- Use `--frozen-lockfile` / `--ci` flags for reproducible installs
- Set `NODE_ENV=production` or equivalent environment variables
- Use `COPY --chown` to avoid permission issues without running as root

#### Health Checks

Include a `HEALTHCHECK` instruction when the app exposes an HTTP endpoint:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/health"] || exit 1
```

For distroless images without wget/curl, use the app's own health endpoint mechanism or skip HEALTHCHECK (orchestrators like Kubernetes handle this externally).

#### Labels

Add OCI-standard labels for traceability:

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/OWNER/REPO"
LABEL org.opencontainers.image.description="Brief description"
```

### Step 4: Generate .dockerignore

If one doesn't exist (or the existing one is sparse), generate a `.dockerignore` that excludes:

```
.git
.github
node_modules
dist
build
*.md
.env*
.vscode
.idea
Dockerfile*
docker-compose*
.dockerignore
coverage
.nyc_output
__pycache__
*.pyc
.pytest_cache
.mypy_cache
bin/
obj/
```

Tailor to the detected language — don't include Python patterns for a Go project.

### Step 5: Generate docker-compose.yml (if requested)

If the user wants one, generate a development-focused `docker-compose.yml` with:
- Volume mounts for live reload
- Port mappings
- Environment variable files
- Dependent services (database, cache) if detected from the project

### Step 6: Provide Build and Run Instructions

After generating files, show the user how to build and run:

```bash
# Build
docker build -t my-app .

# Run
docker run -p 3000:3000 my-app

# Build with BuildKit (recommended)
DOCKER_BUILDKIT=1 docker build -t my-app .
```

Include any framework-specific notes (e.g., Next.js standalone mode requires `output: 'standalone'` in `next.config.js`).

## Language-Specific Patterns

### Node.js / Next.js (Standalone)

Key considerations:
- Use `--frozen-lockfile` for reproducible installs
- For Next.js, enable standalone output and copy `.next/standalone` + `.next/static` + `public/`
- Set `NODE_ENV=production` before the build step for tree-shaking
- Use `node` user in slim images (already exists)

### Go

Key considerations:
- Use `CGO_ENABLED=0` for fully static binaries that work with distroless
- Copy only the binary to the final stage
- Use scratch or distroless/static — Go binaries are self-contained
- Set `GOFLAGS="-trimpath"` and use `-ldflags="-s -w"` to strip debug info

### Python

Key considerations:
- Use `--no-cache-dir` with pip to avoid caching wheels in the image
- For poetry: export to requirements.txt in the build stage, install with pip in the runtime stage
- Use `--no-install-recommends` for apt-get
- Consider using `uv` for faster installs if the project uses it

### C# / .NET Core

Key considerations:
- Use `mcr.microsoft.com/dotnet/sdk:<version>` for the build stage, `mcr.microsoft.com/dotnet/aspnet:<version>-alpine` for runtime
- Restore packages first for cache efficiency: `COPY *.csproj ./` then `dotnet restore`, then copy source and `dotnet publish`
- Use `dotnet publish -c Release -o /app --no-restore` to skip redundant restore in publish
- For self-contained deployments: `dotnet publish -c Release --self-contained -r linux-musl-x64 -p:PublishTrimmed=true` with alpine or distroless
- Enable globalization invariant mode if the app doesn't need culture-specific formatting: `ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=true` (saves ~30MB)
- For multi-project solutions: copy all `.csproj` files preserving directory structure, restore, then copy everything and publish the entry-point project
- Use `app` user in .NET 8+ images (built-in non-root user): `USER app`
- Set `ASPNETCORE_URLS=http://+:8080` (port 8080 is the .NET 8+ default for non-root)
- For minimal APIs or gRPC, consider the `runtime-deps` image instead of `aspnet` if the app is self-contained

### Java (Spring Boot)

Key considerations:
- Use layered jars (`java -Djarmode=layertools -jar app.jar extract`) for cache-friendly layers
- Copy dependencies, spring-boot-loader, snapshot-dependencies, and application as separate layers
- Use jlink for custom JRE if the user wants minimal images
- Set `-XX:+UseContainerSupport` for proper memory detection in containers
