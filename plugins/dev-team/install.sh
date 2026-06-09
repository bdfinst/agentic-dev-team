#!/usr/bin/env bash
# install.sh — Verify prerequisites for the dev-team plugin.
#
# Run this after installing the plugin to confirm all required and optional
# dependencies are available.
#
# Usage:
#   ./install.sh

set -uo pipefail

PASS=0
WARN=0
FAIL=0

check_required() {
  local cmd="$1"
  local install_hint="$2"
  if command -v "$cmd" &>/dev/null; then
    echo "[ok]   $cmd"
    ((PASS++)) || true
  else
    echo "[FAIL] $cmd — required. $install_hint"
    ((FAIL++)) || true
  fi
}

check_optional() {
  local cmd="$1"
  local purpose="$2"
  local install_hint="$3"
  if command -v "$cmd" &>/dev/null; then
    echo "[ok]   $cmd"
    ((PASS++)) || true
  else
    echo "[warn] $cmd — optional ($purpose). $install_hint"
    ((WARN++)) || true
  fi
}

# On Windows the plugin's hooks and helper scripts are bash and require Git Bash
# (the same POSIX shell Claude Code uses for its Bash tool on Windows) — native
# cmd.exe / PowerShell cannot run them. `OS=Windows_NT` is set in every Windows
# shell; Git Bash / MSYS additionally report a MINGW*/MSYS* `uname`. This check
# only fires on Windows, so it is a no-op on macOS and Linux.
check_platform() {
  case "${OS:-}" in
    Windows_NT) ;;
    *) return 0 ;;
  esac
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      echo "[ok]   Git Bash ($(uname -s 2>/dev/null))"
      ((PASS++)) || true
      ;;
    *)
      echo "[FAIL] Windows without Git Bash — this plugin's hooks and helper"
      echo "       scripts need a POSIX bash. Install Git for Windows (Git Bash)"
      echo "       from https://git-scm.com/download/win and run Claude Code from it."
      ((FAIL++)) || true
      ;;
  esac
}

echo "Checking dev-team prerequisites..."
echo ""

echo "--- Required ---"
check_platform
check_required "claude" "Install from https://docs.anthropic.com/en/docs/claude-code"
check_required "jq"     "macOS: brew install jq  |  Linux: apt install jq"
check_required "gh"     "macOS: brew install gh  |  https://cli.github.com/"

echo ""
echo "--- Optional ---"
check_optional "semgrep" \
  "SAST scanning via /semgrep-analyze" \
  "pip install semgrep  |  brew install semgrep"
check_optional "hadolint" \
  "Dockerfile linting via /docker-image-audit" \
  "brew install hadolint  |  https://github.com/hadolint/hadolint/releases"
check_optional "trivy" \
  "image vulnerability scanning via /docker-image-audit" \
  "brew install trivy  |  https://aquasecurity.github.io/trivy/"
check_optional "grype" \
  "second-opinion CVE scanning via /docker-image-audit" \
  "brew install grype  |  https://github.com/anchore/grype"

echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "Result: $FAIL required dependency missing. Install it and re-run."
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo "Result: All required dependencies present. $WARN optional dependency missing (see above)."
  exit 0
else
  echo "Result: All dependencies present."
  exit 0
fi
