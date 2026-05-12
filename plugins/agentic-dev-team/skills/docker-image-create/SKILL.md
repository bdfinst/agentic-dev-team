---
name: docker-image-create
description: Generate production-ready Dockerfiles from project source code. Detects language/framework automatically and produces multi-stage builds with minimal, distroless, or slim base images. Use this skill whenever the user wants to containerize an application, create a Dockerfile, dockerize a project, build a Docker image, or says things like "make this run in Docker", "create a container for this app", "I need a Dockerfile", "package this for deployment", or "containerize this service". Also trigger when the user has an existing Dockerfile and wants it rewritten for production use, or when they ask about Docker best practices for their project.
user-invocable: true
---

# Docker Image Creation

Generate production-ready Dockerfiles by analyzing language, framework, and dependencies. Output is a multi-stage build optimized for small image size, fast builds, and minimal attack surface.

**Default base image strategy**: distroless when possible (only the app and its runtime — no shell, no package manager, no OS utilities; minimal CVE exposure). Fall back to slim (`node:22-slim`, `python:3.12-slim`) when the runtime needs OS-level libraries or a shell for debugging.

## Workflow

### Step 1: Detect the project

Scan the project root to identify:

1. **Language + version** (from version files / configs):
   - `package.json` (Node.js — `engines.node`)
   - `go.mod` (Go — `go` directive)
   - `requirements.txt` / `pyproject.toml` / `Pipfile` (Python — `python_requires` / `.python-version`)
   - `pom.xml` / `build.gradle{,kts}` (Java/Kotlin — `sourceCompatibility`)
   - `*.csproj` / `*.fsproj` (C#/F# — `TargetFramework`)
   - `mix.exs` (Elixir), `Gemfile` (Ruby)

2. **Framework** (drives build command + output structure):
   - Node.js: Next.js, Remix, Express, Fastify, NestJS, Astro, SvelteKit
   - Python: FastAPI, Flask, Django
   - Go: net/http, Gin, Echo, Fiber
   - Java: Spring Boot, Quarkus, Micronaut
   - .NET: ASP.NET Core, Blazor, gRPC, minimal APIs

3. **Package manager** (drives install command):
   - Node.js: npm (`package-lock.json`), yarn (`yarn.lock`), pnpm (`pnpm-lock.yaml`), bun (`bun.lockb`)
   - Python: pip (`requirements.txt`), poetry (`poetry.lock`), pipenv (`Pipfile.lock`), uv (`uv.lock`)

4. **Entry point**: `package.json` `scripts.start` / `main`, `Procfile`, existing Dockerfile `CMD`, or framework convention (`main.go`, `app.py`, `Application.java`).

5. **Existing Docker artifacts**: `.dockerignore`, existing `Dockerfile`, `docker-compose.yml`.

Present a detection summary to the user and ask: "Want me to adjust anything before generating?"

### Step 2: Ask about registry and build tools

Ask:

1. **Container registry?** (Docker Hub, ghcr.io, ECR, GCR, ACR) — affects `FROM` paths and login steps.
2. **Build tool?** Default: BuildKit (`DOCKER_BUILDKIT=1`). Enables cache mounts, secret mounts, and parallel stages.
3. **Generate `.dockerignore`?** If missing or sparse.
4. **Generate `docker-compose.yml`?** For local development.

Proceed with sensible defaults if the user says "just go with defaults."

### Step 3: Generate the Dockerfile

**Layer order** (least-changed → most-changed) for cache efficiency: base image → system deps → dependency manifest + install → source code → build → final stage with only the runtime artifact.

**Cache-friendly install** — copy manifests first, install, then copy source:

```dockerfile
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build
```

Never `COPY . .` before install — busts the cache on every source change.

**Stages**: `deps` (install) → `build` (compile/bundle) → `runtime` (minimal base with artifact only). Two stages suffice for interpreted languages without a build step.

**Base image table**:

| Language | Build stage | Runtime stage |
|---|---|---|
| Go | `golang:<version>` | `gcr.io/distroless/static-debian12` |
| Java | `eclipse-temurin:<version>` | `gcr.io/distroless/java21-debian12` |
| Node.js | `node:<version>` | `node:<version>-slim` or `gcr.io/distroless/nodejs22-debian12` |
| Python | `python:<version>` | `python:<version>-slim` |
| .NET | `mcr.microsoft.com/dotnet/sdk:<version>` | `mcr.microsoft.com/dotnet/aspnet:<version>-alpine` |

Pin major.minor (e.g., `node:22.12`, not `node:latest`). Digest-pin only for high-security environments.

**Security defaults**:
- Run as non-root in the final stage (`USER nonroot` for distroless; create a user for slim bases)
- Never copy `.env`, secrets, or credentials into the image
- Use `--frozen-lockfile` / `--ci` for reproducible installs
- Set `NODE_ENV=production` or equivalent
- Use `COPY --chown` to set ownership without running as root

**Health checks** (when the app exposes HTTP):

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/health"] || exit 1
```

Distroless images lack `wget`/`curl` — skip HEALTHCHECK and rely on the orchestrator (Kubernetes liveness probes etc.).

**OCI labels**:

```dockerfile
LABEL org.opencontainers.image.source="https://github.com/OWNER/REPO"
LABEL org.opencontainers.image.description="Brief description"
```

### Step 4: Generate .dockerignore

If absent or sparse, write one tailored to the detected language. Common patterns:

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

Drop language-irrelevant patterns (no Python patterns for a Go project).

### Step 5: Generate docker-compose.yml (if requested)

Development-focused: volume mounts for live reload, port mappings, env-file references, dependent services (database, cache) if detected.

### Step 6: Provide build and run instructions

```bash
docker build -t my-app .
docker run -p 3000:3000 my-app

# With BuildKit
DOCKER_BUILDKIT=1 docker build -t my-app .
```

Include framework-specific notes (e.g., Next.js standalone mode requires `output: 'standalone'` in `next.config.js`).

## Language-specific patterns

### Node.js / Next.js (standalone)
- `--frozen-lockfile` for reproducible installs
- For Next.js: enable standalone output and copy `.next/standalone` + `.next/static` + `public/`
- Set `NODE_ENV=production` before the build step (for tree-shaking)
- Use the `node` user (built-in to slim images)

### Go
- `CGO_ENABLED=0` for fully static binaries (works with distroless/static)
- Copy only the binary to the final stage
- Use scratch or distroless/static — Go binaries are self-contained
- Strip debug info: `GOFLAGS="-trimpath"` + `-ldflags="-s -w"`

### Python
- `--no-cache-dir` with pip (don't bake wheels into the image)
- Poetry: export to requirements.txt in the build stage, pip-install in runtime
- `--no-install-recommends` for `apt-get`
- Consider `uv` for faster installs

### C# / .NET
- Build stage `mcr.microsoft.com/dotnet/sdk:<version>`; runtime `mcr.microsoft.com/dotnet/aspnet:<version>-alpine`
- Restore first for cache efficiency: `COPY *.csproj ./` → `dotnet restore` → copy source → `dotnet publish`
- `dotnet publish -c Release -o /app --no-restore` (skip redundant restore)
- Self-contained: `dotnet publish -c Release --self-contained -r linux-musl-x64 -p:PublishTrimmed=true`
- Globalization invariant if no culture-specific formatting: `ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=true` (saves ~30MB)
- Multi-project solutions: copy all `.csproj` preserving structure, restore, copy everything, publish entry-point project
- `USER app` (built-in non-root in .NET 8+), `ASPNETCORE_URLS=http://+:8080` (default for non-root)

### Java (Spring Boot)
- Layered jars: `java -Djarmode=layertools -jar app.jar extract`; copy dependencies, spring-boot-loader, snapshot-dependencies, application as separate layers
- `jlink` for custom minimal JRE
- `-XX:+UseContainerSupport` for correct memory detection in containers
