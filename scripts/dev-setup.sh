#!/usr/bin/env bash
# dev-setup.sh — validate and install the toolchain plugin development needs.
#
# The local pre-push gate (scripts/ci-local.sh) and the GitHub CI jobs in
# .github/workflows/plugin-tests.yml require a fixed set of CLI tools plus the
# Python dev dependencies. ci-local.sh only *checks* for them and aborts with a
# message; this script *installs* whatever is missing so a fresh checkout is
# ready to run the gates.
#
# Idempotent and safe to re-run: present tools are left untouched. CLI tools are
# installed via the platform package manager — Homebrew on macOS, apt-get on
# Debian/Ubuntu. Python deps come from requirements-dev.txt.
#
# Usage:
#   bash scripts/dev-setup.sh
#
# Relationship to /setup: when that skill (plugins/dev-team/skills/setup/
# SKILL.md) detects it is running inside this repo, it shells out to this
# script rather than reimplementing its install logic. This script stays a
# separate bash entry point on purpose — it must work before Claude Code or
# the plugin is installed, and it is reused as a generic template by
# /new-marketplace for other marketplace repos — so it does not become a
# wrapper around the skill.
#
# Exit codes:
#   0  every requirement is satisfied
#   1  one or more requirements could not be installed (details printed)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# --- output helpers --------------------------------------------------------
bold=$(tput bold 2>/dev/null || true)
red=$(tput setaf 1 2>/dev/null || true)
green=$(tput setaf 2 2>/dev/null || true)
yellow=$(tput setaf 3 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

section() { printf '\n%s== %s ==%s\n' "$bold" "$1" "$reset"; }
ok()      { printf '  %s✓%s %s\n' "$green" "$reset" "$1"; }
warn()    { printf '  %s∼%s %s\n' "$yellow" "$reset" "$1"; }
err()     { printf '  %s✗%s %s\n' "$red" "$reset" "$1" >&2; }

FAILURES=0
note_failure() { FAILURES=$((FAILURES + 1)); }

# --- package-manager detection ---------------------------------------------
PM=""
if command -v brew >/dev/null 2>&1; then
  PM="brew"
elif command -v apt-get >/dev/null 2>&1; then
  PM="apt"
fi

SUDO=""
if [ "$PM" = "apt" ] && [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

APT_UPDATED=0
apt_update_once() {
  [ "$APT_UPDATED" -eq 1 ] && return 0
  $SUDO apt-get update -y >/dev/null 2>&1 || true
  APT_UPDATED=1
}

# Map a logical tool name to its package name for the active package manager.
# Every tool name currently matches its package name 1:1 (the one divergent
# case, brew's bats -> bats-core, was retired with bats-core itself in #677).
pkg_name() {
  echo "$1"
}

install_pkg() {
  local pkg="$1"
  case "$PM" in
    brew) brew install "$pkg" ;;
    apt)  apt_update_once; $SUDO apt-get install -y "$pkg" ;;
    *)    return 1 ;;
  esac
}

# Ensure a CLI tool is present, installing it if missing. Returns non-zero if it
# is still absent afterwards.
ensure_tool() {
  local tool="$1" optional="${2:-required}"
  if command -v "$tool" >/dev/null 2>&1; then
    ok "$tool ($(command -v "$tool"))"
    return 0
  fi
  if [ -z "$PM" ]; then
    if [ "$optional" = "optional" ]; then
      warn "$tool missing; no supported package manager (brew/apt) to install it — skipping (optional)"
      return 0
    fi
    err "$tool missing and no supported package manager (brew/apt) found — install it manually"
    note_failure
    return 1
  fi
  printf '  installing %s …\n' "$tool"
  if install_pkg "$(pkg_name "$tool")" >/dev/null 2>&1 && command -v "$tool" >/dev/null 2>&1; then
    ok "$tool installed ($(command -v "$tool"))"
    return 0
  fi
  if [ "$optional" = "optional" ]; then
    warn "could not install $tool (optional) — continuing"
    return 0
  fi
  err "could not install $tool via $PM — install it manually"
  note_failure
  return 1
}

# --- required CLI tools ----------------------------------------------------
section "CLI tools"
if [ -z "$PM" ]; then
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      # Git Bash on Windows — the supported Windows shell, but it has no native
      # package manager, so install missing tools with scoop/winget/choco.
      warn "Git Bash detected (no brew/apt) — will verify tools but cannot auto-install;"
      warn "  install missing ones with: scoop install <tool>  (or winget/choco)"
      ;;
    *)
      if [ "${OS:-}" = "Windows_NT" ]; then
        err "Windows without Git Bash — the plugin's bash scripts need a POSIX shell."
        err "  Install Git for Windows (Git Bash): https://git-scm.com/download/win"
        note_failure
      else
        warn "no Homebrew or apt-get detected — will verify tools but cannot auto-install"
      fi
      ;;
  esac
fi
for tool in jq python3; do
  ensure_tool "$tool" required
done
# shellcheck is NOT installed here on purpose. It is version-PINNED
# (SHELLCHECK_VERSION in scripts/ci-local.sh), and a package manager gives
# whatever it happens to ship — Homebrew's 0.11.0 and Ubuntu's 0.9.0 disagree
# on real findings, which is the drift the pin exists to remove.
# ci-local.sh's _resolve_shellcheck fetches the pinned release binary into
# ~/.cache/agentic-dev-team/ on first use, so nothing to do here.
ensure_tool shellcheck optional
# gh is used for PR operations in CI/cloud, not by the local gates — best effort.
ensure_tool gh optional

# --- Python 3.10, the shipped floor ---------------------------------------
# ci-local.sh's chk_python_floor makes a real 3.10 byte-compile and import the
# shipped tree, then (#1650) actually RUN the shipped-agent-script test slice
# under that interpreter via `uv run --python` — so uv is now an unconditional
# requirement of the gate, not just a fallback for locating 3.10 itself. That
# check FAILS rather than skips when either is missing, so provision both
# here — a gate that silently downgrades on the machines least likely to have
# them is no gate at all.
section "Python 3.10 (shipped floor — ADR 0031) + uv"
if ! command -v uv >/dev/null 2>&1; then
  warn "installing uv (fetches the 3.10 floor interpreter and runs the floor-interpreter test slice)"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
  export PATH="$HOME/.local/bin:$PATH"
fi
if command -v uv >/dev/null 2>&1; then
  ok "uv ($(uv --version 2>&1))"
else
  warn "could not install uv — chk_python_floor will fail until you do"
  warn "  see: https://docs.astral.sh/uv/"
fi
if command -v python3.10 >/dev/null 2>&1; then
  ok "python3.10 ($(python3.10 -V 2>&1))"
elif command -v uv >/dev/null 2>&1 && uv python find 3.10 >/dev/null 2>&1; then
  ok "python3.10 via uv ($(uv python find 3.10))"
elif command -v uv >/dev/null 2>&1 && uv python install 3.10 >/dev/null 2>&1; then
  ok "python3.10 installed via uv"
else
  warn "could not provision Python 3.10 — chk_python_floor will fail until you do"
  warn "  try: uv python install 3.10   (or install a python3.10 package)"
fi

# --- pip ------------------------------------------------------------------
section "Python package manager (pip)"
if python3 -m pip --version >/dev/null 2>&1; then
  ok "pip ($(python3 -m pip --version 2>/dev/null))"
else
  printf '  bootstrapping pip …\n'
  if [ "$PM" = "apt" ]; then
    install_pkg python3-pip >/dev/null 2>&1 || true
  fi
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
  if python3 -m pip --version >/dev/null 2>&1; then
    ok "pip ready"
  else
    err "pip is unavailable — install python3-pip, then re-run"
    note_failure
  fi
fi

# --- Python dev dependencies ----------------------------------------------
section "Python dev dependencies (requirements-dev.txt)"

# Are the requirements-dev.txt deps already installed? Probe importability of
# every declared distribution (find_spec locates without importing, so this
# stays fast) plus the one CLI-only wheel (ruff ships a console script, no
# importable module). When all are present we skip the pip install entirely
# instead of re-resolving on every run — only missing tools get installed
# (issue #1236). The module list mirrors requirements-dev.txt; keep it in sync.
dev_deps_satisfied() {
  python3 - <<'PY' >/dev/null 2>&1
import importlib.util, sys
mods = ["yaml", "httpx", "jsonschema", "pytest",
        "pytest_asyncio", "xdist", "pytest_cov", "semgrep", "mypy"]
# ruff is probed as an importable MODULE, not via shutil.which (#1676):
# chk_ruff runs `python3 -m ruff`, so a stray PATH binary at some other
# version must not satisfy this check and skip the pinned install.
mods.append("ruff")
sys.exit(1 if any(importlib.util.find_spec(m) is None for m in mods) else 0)
PY
}

if ! python3 -m pip --version >/dev/null 2>&1; then
  warn "skipping requirements-dev.txt — pip not available"
elif dev_deps_satisfied; then
  ok "requirements-dev.txt already satisfied — nothing to install"
else
  # Try a normal install first; fall back to the escape hatches newer distros
  # need (PEP 668 "externally-managed-environment", or no write access to the
  # system site-packages).
  if python3 -m pip install --quiet -r requirements-dev.txt \
     || python3 -m pip install --quiet --user -r requirements-dev.txt \
     || python3 -m pip install --quiet --break-system-packages -r requirements-dev.txt; then
    ok "installed from requirements-dev.txt"
  else
    err "pip install -r requirements-dev.txt failed — consider a virtualenv:"
    err "  python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt"
    note_failure
  fi
fi

# --- Graphify (code knowledge graph) ---------------------------------------
# Graphify turns the repo into a queryable multi-modal knowledge graph. We use
# its native Claude integration: `graphify install --project` writes the
# /graphify skill + a CLAUDE.md section + PreToolUse nudge hooks (all committed,
# so this only refreshes them), and the graph is rebuilt on commit. Install as
# an isolated CLI app (uv/pipx), NOT into the repo's Python env. Optional and
# best-effort throughout: absence never fails setup.
section "Graphify (code knowledge graph)"
# Graphify auto-selects a semantic-pass backend from whichever provider key is
# present. The `gemini` backend (selected by GEMINI_API_KEY or GOOGLE_API_KEY —
# see .claude/skills/graphify/SKILL.md) routes through an OpenAI-compatible
# client and needs the `[gemini]` extra — a plain `graphifyy` install leaves
# `graphify extract .` failing every semantic chunk the first time it runs
# with only that key set (issue #1483). Install the matching extra up front
# when that's the key we detect; other backends (claude, openai) need no
# extra.
GRAPHIFY_SPEC="graphifyy"
if { [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; } && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  GRAPHIFY_SPEC="graphifyy[gemini]"
fi
if command -v graphify >/dev/null 2>&1; then
  ok "graphify ($(graphify --version 2>/dev/null | head -1))"
  # Idempotent repair: a machine that already has plain `graphifyy` installed
  # (the exact state issue #1483 was filed from) is the population this fix
  # exists for — re-running dev-setup.sh must actually add the missing extra,
  # not short-circuit on `command -v graphify` and leave it broken.
  if [ "$GRAPHIFY_SPEC" != "graphifyy" ]; then
    if command -v uv >/dev/null 2>&1; then
      printf '  repairing graphify install with %s …\n' "$GRAPHIFY_SPEC"
      if uv tool install "$GRAPHIFY_SPEC" --force >/dev/null 2>&1; then
        ok "graphify backend extra repaired via uv"
      else
        warn "uv tool install --force failed (optional) — install manually: uv tool install '$GRAPHIFY_SPEC' --force"
      fi
    elif command -v pipx >/dev/null 2>&1; then
      printf '  repairing graphify install with %s …\n' "$GRAPHIFY_SPEC"
      if pipx install "$GRAPHIFY_SPEC" --force >/dev/null 2>&1; then
        ok "graphify backend extra repaired via pipx"
      else
        warn "pipx install --force failed (optional) — install manually: pipx install '$GRAPHIFY_SPEC' --force"
      fi
    else
      warn "graphify backend extra may be missing — install manually: pip install --user --upgrade '$GRAPHIFY_SPEC'"
    fi
  fi
elif command -v uv >/dev/null 2>&1; then
  printf '  installing %s via uv …\n' "$GRAPHIFY_SPEC"
  if uv tool install "$GRAPHIFY_SPEC" >/dev/null 2>&1; then
    ok "graphify installed via uv"
  else
    warn "uv tool install failed (optional) — install manually: uv tool install '$GRAPHIFY_SPEC'"
  fi
elif command -v pipx >/dev/null 2>&1; then
  printf '  installing %s via pipx …\n' "$GRAPHIFY_SPEC"
  if pipx install "$GRAPHIFY_SPEC" >/dev/null 2>&1; then
    ok "graphify installed via pipx"
  else
    warn "pipx install failed (optional) — install manually: pipx install '$GRAPHIFY_SPEC'"
  fi
elif python3 -m pip --version >/dev/null 2>&1; then
  printf '  installing %s via pip --user …\n' "$GRAPHIFY_SPEC"
  if python3 -m pip install --quiet --user "$GRAPHIFY_SPEC" >/dev/null 2>&1; then
    ok "graphify installed via pip --user"
  else
    warn "pip install failed (optional) — install manually: pip install --user '$GRAPHIFY_SPEC'"
  fi
else
  warn "no uv/pipx/pip to install graphify (optional) — see https://github.com/Graphify-Labs/graphify"
fi

# Regenerate graphify's git hooks for this clone. NOTE: we deliberately do NOT
# run `graphify install --project` — its CLAUDE.md editor rewrites our curated
# file (it treats a prior graphify mention as an anchor and drops everything to
# the next heading). The .claude wiring is committed once instead. `hook install`
# only (re)writes .husky/post-commit + post-checkout, which graphify targets
# directly because git hooks route through husky (core.hooksPath); those carry a
# machine-specific Python path, so they're gitignored and regenerated per-clone.
if command -v graphify >/dev/null 2>&1; then
  if graphify hook install >/dev/null 2>&1; then
    ok "graphify git hooks installed (rebuild-on-commit)"
  else
    warn "graphify hook install failed (optional)"
  fi
fi

# --- verification ----------------------------------------------------------
# Re-check everything from scratch so the summary reflects the real end state,
# not what we believe we installed.
section "Verifying"
for tool in jq python3 uv; do
  if command -v "$tool" >/dev/null 2>&1; then
    ok "$tool"
  else
    err "$tool still missing"
    note_failure
  fi
done

# Python imports several dev gates rely on (yaml + httpx) and the semgrep CLI.
for mod in yaml httpx; do
  if python3 -c "import $mod" >/dev/null 2>&1; then
    ok "python module: $mod"
  else
    err "python module '$mod' not importable (declared in requirements-dev.txt)"
    note_failure
  fi
done
if command -v semgrep >/dev/null 2>&1 || python3 -c "import semgrep" >/dev/null 2>&1; then
  ok "semgrep"
else
  warn "semgrep not found — only needed if you run/modify the security-assessment plugin"
fi

# graphify (optional). Native integration; build the repo graph on demand with
# `graphify extract .` — the committed CLAUDE.md section + hooks then take over.
if command -v graphify >/dev/null 2>&1; then
  ok "graphify"
else
  warn "graphify not found (optional) — a code knowledge graph for this repo; see CLAUDE.md Prerequisites"
fi

# --- Java static-analysis lane (warn-only) ---------------------------------
# PMD backs /build's Java lane in downstream Java projects; this repo has no
# Java code, so absence never fails setup.
if command -v pmd >/dev/null 2>&1; then
  ok "pmd"
else
  warn "pmd not found — only needed for Java projects; install repo-locally with: python3 plugins/dev-team/scripts/install-java-static-analysis.py"
fi

# ruff + mypy arrive via requirements-dev.txt (pip), like semgrep — verify the
# CLIs the Python static-analysis lane probes for.
for pytool in ruff mypy; do
  if command -v "$pytool" >/dev/null 2>&1; then
    ok "$pytool"
  else
    err "$pytool not found (declared in requirements-dev.txt)"
    note_failure
  fi
done

# --- summary ---------------------------------------------------------------
section "Summary"
if [ "$FAILURES" -eq 0 ]; then
  printf '%s%sDev environment ready.%s Run the local gates with: bash scripts/ci-local.sh\n' \
    "$bold" "$green" "$reset"
  exit 0
fi
printf '%s%s%d requirement(s) could not be satisfied — see the messages above.%s\n' \
  "$bold" "$red" "$FAILURES" "$reset" >&2
exit 1
