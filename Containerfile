# Containerfile — reproducible dev/CI environment for agentic-dev-team.
#
# Mirrors the toolchain the local gates need (scripts/ci-local.sh, run by the
# pre-push hook) and the cloud setup (.claude/cloud-setup.sh). Modelled on
# setup-prereqs-linux.sh's apt path, pinned to an Ubuntu base so it matches the
# Ubuntu VMs used by Claude Code on the web and GitHub Actions.
#
# What it provides:
#   * hard deps:        jq, shellcheck, python3 + pip, git
#   * Python dev deps:  requirements-dev.txt (PyYAML, semgrep, httpx, pytest,
#                       ruff, mypy, …) — the same set CI installs
#   * Node 24+:         drives husky hooks, eslint, commitlint (engines floor)
#   * gh CLI:           PR operations in CI/cloud
#
# Build:
#   podman build -t agentic-dev-team:dev .
#
# Run an interactive shell with the repo mounted (SELinux-safe :Z relabel):
#   podman run --rm -it -v "$PWD":/workspace:Z agentic-dev-team:dev
#
# Run the local gates non-interactively:
#   podman run --rm -v "$PWD":/workspace:Z agentic-dev-team:dev \
#     bash scripts/ci-local.sh
#
# See docs/podman-dev-environment.md for the full walkthrough.

FROM ubuntu:24.04

# Single source of truth for the Node major version mirrors .nvmrc (fallback 24).
ARG NODE_MAJOR=24

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- Hard dependencies + build basics --------------------------------------
# jq, shellcheck, python3/pip, git are what ci-local.sh checks for up front.
# curl/ca-certificates/gnupg bootstrap the NodeSource and GitHub CLI apt repos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        git \
        jq \
        shellcheck \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# --- Node (engines floor >=24, from .nvmrc) --------------------------------
# husky's `prepare` script + lint-staged/commitlint/eslint need Node; the repo's
# package.json engines floor is >=24, enforced by engine-strict in .npmrc.
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI (PR operations in CI/cloud) --------------------------------
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# The repo is bind-mounted at run time and owned by the host user, so git flags
# it as "dubious ownership" and refuses to operate. Trust it inside the image so
# ci-local.sh and the git-driven test suites run without extra setup.
RUN git config --system --add safe.directory /workspace

# --- Python dev dependencies (requirements-dev.txt) ------------------------
# Copied and installed first so the layer caches independently of source churn.
# Ubuntu 24.04's pip is PEP 668 externally-managed; --break-system-packages is
# the intended escape hatch inside a disposable container (mirrors dev-setup.sh's
# fallback), keeping the deps on the system interpreter the gates invoke.
COPY requirements-dev.txt ./
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        -r requirements-dev.txt

# --- Node dev dependencies -------------------------------------------------
# Prime the npm layer from the lockfile so `npm ci` is cached across source-only
# rebuilds. HUSKY=0 stops husky's `prepare` from trying to install git hooks at
# build time (there is no .git in the build context); hooks are (re)installed by
# `npm ci` when you mount the real repo and run it.
COPY package.json package-lock.json ./
RUN HUSKY=0 npm ci

# Default to an interactive shell; override with the command you want to run.
CMD ["bash"]
