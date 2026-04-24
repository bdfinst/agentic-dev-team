#!/usr/bin/env bash
# install-macos.sh — install the tools the agentic-security-review plugin calls.
#
# Companion to install.sh (which only verifies presence). This script runs the
# actual brew / pip commands on macOS.
#
# Usage:
#   ./install-macos.sh                # install tier-1 tools (recommended default)
#   ./install-macos.sh --all          # tier-1 + optional + red-team / PDF deps
#   ./install-macos.sh --dry-run      # print commands without running them
#   ./install-macos.sh --help
#
# Safe to re-run: each step checks presence first and skips when already
# installed. Homebrew self-update is suppressed (HOMEBREW_NO_AUTO_UPDATE=1).
#
# Exit codes:
#   0  — all requested installs succeeded (or were already present)
#   1  — missing prerequisite (brew, python3) or one install failed
#   2  — bad flag

set -uo pipefail

MODE="tier1"    # tier1 | all
DRY_RUN=0

print_help() {
  cat <<'EOF'
install-macos.sh — install agentic-security-review tool dependencies on macOS.

Groups:
  tier-1 (default): python3, jq, semgrep, gitleaks, trivy, hadolint, actionlint
  --all adds:       checkov, bandit, gosec, bearer, osv-scanner, grype,
                    kube-linter, trufflehog, detect-secrets, deptry,
                    kube-score, govulncheck, pandoc, weasyprint

Flags:
  --all         install every tool the plugin can call
  --dry-run     print the commands without running them
  --help        show this message

Prerequisites:
  Homebrew (https://brew.sh) — hard requirement. The script refuses to run
  without it; we will not auto-install Homebrew on your behalf.
  python3 — macOS ships with it, but version >= 3.10 is required for the
  red-team harness.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --help|-h) print_help; exit 0 ;;
    --all) MODE="all"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown flag: $1" >&2; print_help; exit 2 ;;
  esac
done

# ── Platform + prerequisite gate ────────────────────────────────────────────

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: this script targets macOS. On Linux, use apt/pip equivalents from install.sh's hints." >&2
  exit 1
fi

if ! command -v brew &>/dev/null; then
  echo "error: Homebrew not found. Install it first: https://brew.sh" >&2
  echo "       /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"" >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "error: python3 not on PATH." >&2
  echo "       macOS ships with python3; verify your PATH or install via 'brew install python@3.12'" >&2
  exit 1
fi

PYMAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PYMINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
if (( PYMAJOR < 3 || (PYMAJOR == 3 && PYMINOR < 10) )); then
  echo "error: python3 $(python3 --version) found; red-team harness requires >= 3.10" >&2
  echo "       upgrade: brew install python@3.12 && brew link --overwrite python@3.12" >&2
  exit 1
fi

export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_UPGRADE=1

# ── Helpers ────────────────────────────────────────────────────────────────

section() { echo ""; echo "── $* ──"; }

run() {
  # Pretty-print and execute (or skip when --dry-run).
  printf '  $ %s\n' "$*"
  if (( DRY_RUN == 0 )); then
    "$@"
  fi
}

INSTALLED=0
SKIPPED=0
FAILED=()

brew_install() {
  # brew_install <formula> [<binary-check-name>]
  local pkg="$1"
  local probe="${2:-$1}"
  if command -v "$probe" &>/dev/null; then
    printf '  [skip] %-16s — already installed\n' "$pkg"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi
  if run brew install --quiet "$pkg"; then
    INSTALLED=$((INSTALLED + 1))
  else
    printf '  [FAIL] %s — brew install failed\n' "$pkg"
    FAILED+=("$pkg")
  fi
}

pip_install() {
  # pip_install <package> [<binary-check-name>]
  local pkg="$1"
  local probe="${2:-$1}"
  if command -v "$probe" &>/dev/null; then
    printf '  [skip] %-16s — already installed\n' "$pkg"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi
  # Use pipx when available (isolates CLI tools); fall back to user pip.
  if command -v pipx &>/dev/null; then
    if run pipx install "$pkg"; then
      INSTALLED=$((INSTALLED + 1))
    else
      FAILED+=("$pkg")
    fi
  else
    if run python3 -m pip install --user --quiet "$pkg"; then
      INSTALLED=$((INSTALLED + 1))
    else
      FAILED+=("$pkg")
    fi
  fi
}

# ── Tier-1 baseline (always installed) ─────────────────────────────────────

section "Tier-1 baseline — required for /security-assessment to be useful"

brew_install jq
# semgrep: brew has it, but pip/pipx is the upstream-recommended path.
if ! command -v semgrep &>/dev/null; then
  pip_install semgrep
else
  printf '  [skip] %-16s — already installed\n' semgrep
  SKIPPED=$((SKIPPED + 1))
fi
brew_install gitleaks
brew_install trivy
brew_install hadolint
brew_install actionlint

# ── Optional + red-team deps (with --all) ──────────────────────────────────

if [[ "$MODE" == "all" ]]; then
  section "Optional SAST / policy / supply-chain"
  pip_install checkov
  pip_install bandit
  brew_install gosec
  brew_install bearer
  brew_install osv-scanner
  brew_install grype
  brew_install kube-linter
  brew_install trufflehog
  pip_install detect-secrets
  pip_install deptry
  brew_install kube-score
  # govulncheck: requires Go toolchain. Install go first if absent.
  if command -v go &>/dev/null; then
    if ! command -v govulncheck &>/dev/null; then
      run go install golang.org/x/vuln/cmd/govulncheck@latest && INSTALLED=$((INSTALLED + 1))
    else
      printf '  [skip] %-16s — already installed\n' govulncheck
      SKIPPED=$((SKIPPED + 1))
    fi
  else
    printf '  [skip] %-16s — Go toolchain absent; skipping (brew install go to enable)\n' govulncheck
    SKIPPED=$((SKIPPED + 1))
  fi

  section "Red-team / PDF export deps"
  brew_install pandoc
  pip_install weasyprint
fi

# ── Summary ────────────────────────────────────────────────────────────────

section "Summary"
printf '  installed: %d   skipped (already present): %d   failed: %d\n' \
  "$INSTALLED" "$SKIPPED" "${#FAILED[@]}"

if (( ${#FAILED[@]} > 0 )); then
  echo ""
  printf '  failed packages: %s\n' "${FAILED[*]}"
  echo "  Re-run with --dry-run to inspect the failing commands, or install the"
  echo "  failing packages manually."
  exit 1
fi

echo ""
echo "  Done. Verify the install:"
echo "    ./plugins/agentic-security-review/install.sh"
echo ""
echo "  Then try: /security-assessment <path-to-target>"
exit 0
