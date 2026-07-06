# Capability-tools registry

Single source of truth for the **capability tools** that `/project-init`
installs beyond the four static-analysis lanes (JS/TS, Python, C#, Java).
These are the CLIs and browsers that other skills and agents depend on. The
skill's Step 4b reads this table: it runs each tool's **offer-when** signal,
presents the warranted tools as their own group in the three-column plan,
installs only the missing + confirmed ones with the **OS-aware install**
command, and probes them with the **verify** command in Step 5.

Detection-gated by design: a tool is only offered when its signal fires, so a
Python-only repo with no Dockerfile is never asked about the docker scanners.
Every offer is confirmed before anything installs — same gate as the lanes.

## Install-level honesty

The "always repo-level, never user/system" rule of the static-analysis lanes
applies to **lane tools + Playwright**. The other capability tools are CLIs
that are user/system-level by nature (`brew`, `pipx`, apt) — there is no
repo-local install for a general-purpose CLI like `gh` or `semgrep`. So:

- **Playwright** is the **repo-level exception among capability tools**: it
  installs as an `npm` devDependency (`@playwright/test`), versioned with the
  project, exactly like a lane tool. Only its Chromium browser download is
  machine-level (a Playwright cache, not a repo file).
- **semgrep, adr, gh, hadolint, trivy, grype** are **user/system-level**
  CLIs. Install them with the OS package manager (or pipx/user-pip on Linux).
  This is the deliberate, documented exception to "always repo-level".

## Registry

| Tool | Skills that need it | Offer-when signal | OS-aware install command | Verify probe |
| --- | --- | --- | --- | --- |
| **semgrep** | `/semgrep-analyze`, security-assessment | Any source lane detected (universal SAST) — opt-in, confirmable | macOS: `brew install semgrep`. Linux: `pipx install semgrep` (fallback `python3 -m pip install --user semgrep`). Windows: `pipx install semgrep`. | `semgrep --version` |
| **Playwright + Chromium** | `/benchmark`, `/browse`, `/browser-testing`, `/performance-benchmark` | Frontend signals in an **existing** project: React/Svelte/Vue/Angular/Next/Nuxt/SvelteKit/Astro deps, or an `e2e/` dir, or a `playwright.config.*` file. (Greenfield JS scaffold installs it separately.) | Repo-level (npm devDependency): `npm i -D @playwright/test && npx playwright install chromium` | `npx --no-install playwright --version` |
| **adr** (npryce/adr-tools) | `/adr-tools`, adr-author agent | `docs/adr/`, `docs/decisions/`, or existing ADR `*.md` files present | macOS: `brew install adr-tools`. Linux/Windows: `git clone https://github.com/npryce/adr-tools` and put its `src/` on `PATH` (e.g. symlink into `~/.local/bin`). | `adr help` |
| **gh** (GitHub CLI) | `/issues-from-assessment` and other issue/PR skills | Git repo with a GitHub remote — `git remote -v` shows `github.com` | macOS: `brew install gh`. Linux: official apt repo (`cli.github.com`), or `webi`/binary download. Windows: `winget install GitHub.cli`. | `gh --version` |
| **hadolint** | `/docker-image-audit` | A `Dockerfile`, `*.dockerfile`, or `compose.y*ml` present | macOS: `brew install hadolint`. Linux/Windows: official release binary from `hadolint/hadolint`. | `hadolint --version` |
| **trivy** | `/docker-image-audit` | Same docker signal as hadolint | macOS: `brew install trivy`. Linux/Windows: official install script / release binary from `aquasecurity/trivy`. | `trivy --version` |
| **grype** | `/docker-image-audit` | Same docker signal as hadolint | macOS: `brew install grype`. Linux/Windows: official install script / release binary from `anchore/grype`. | `grype --version` |
| **codegraph** | code-intelligence (`codegraph_context`/`codegraph_explore` MCP tools, `codegraph-nudge` hook) | Universal — opt-in, confirmable, offered on every repo like semgrep | Install/init is a multi-step state machine, not a single command — see Step 4c and [`codegraph-vs-graphify.md`](../../../knowledge/codegraph-vs-graphify.md). Manual install: `https://github.com/colbymchenry/codegraph#installation`. | `command -v codegraph`, `.codegraph/` present |
| **graphify** | `/graphify` (native skill, this repo's own `.claude/skills/graphify/`), architecture/onboarding questions spanning code + docs | Universal — opt-in, confirmable | `uv tool install graphifyy` (fallback `pipx install graphifyy`, fallback `python3 -m pip install --user graphifyy`), then `graphify install --project` and `graphify hook install` — see Step 4c for the CLAUDE.md corruption guard this install requires. | `graphify --version` |

macOS one-liner for the docker scanners: `brew install hadolint trivy grype`.

**codegraph and graphify get their own step (4c)**, not just a table row: codegraph's install+init flow is a stateful branch (installed × initialized), and graphify's install writes to the target repo's own `CLAUDE.md` and needs a corruption guard — both too complex for a single table row's install command. See `SKILL.md` Step 4c.

## OS awareness

Mirror the OS detection used by `/setup` — `uname -s` → `Darwin`
(macOS, brew), `Linux` (apt/dnf/yum/pacman, else pipx/user-pip/binary),
`MINGW*`/`MSYS*` (Windows Git Bash, winget/choco/scoop). WSL reports `Linux`
and follows the Linux column. When no package manager is detected, print the
manual install pointer from the table and continue — a missing capability
tool degrades the dependent skill gracefully; it never fails `/project-init`.
