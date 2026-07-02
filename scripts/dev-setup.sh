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
for tool in jq shellcheck python3; do
  ensure_tool "$tool" required
done
# gh is used for PR operations in CI/cloud, not by the local gates — best effort.
ensure_tool gh optional

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
if python3 -m pip --version >/dev/null 2>&1; then
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
else
  warn "skipping requirements-dev.txt — pip not available"
fi

# --- verification ----------------------------------------------------------
# Re-check everything from scratch so the summary reflects the real end state,
# not what we believe we installed.
section "Verifying"
for tool in jq shellcheck python3; do
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
