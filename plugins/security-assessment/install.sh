#!/usr/bin/env bash
# install.sh — verify prerequisites for the agentic-security-assessment plugin.
#
# Checks (in order):
#   1. agentic-dev-team is installed with a compatible primitives-contract
#      version (^1.0.0). Hard failure on mismatch or missing.
#   2. Python >= 3.10 for the red-team harness. Hard failure if absent.
#   3. Tier-1 tool presence, grouped by capability tier. Required tools are
#      shown with [REQUIRED] prefix; absence is hard failure. Optional tools
#      absence emits warnings.
#   4. Prints the exact settings.local.json opt-out snippet for hooks.
#
# Exit codes:
#   0  — all hard checks pass; some optional tools may be missing
#   1  — one or more hard checks failed
#
# Usage:
#   ./install.sh           # run checks
#   ./install.sh --help

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve repo root by walking up until .claude-plugin/marketplace.json is seen.
REPO_ROOT=""
for anchor_dir in "$SCRIPT_DIR" "$SCRIPT_DIR/.." "$SCRIPT_DIR/../.." "$SCRIPT_DIR/../../.."; do
  if [ -f "$anchor_dir/.claude-plugin/marketplace.json" ]; then
    REPO_ROOT="$(cd "$anchor_dir" && pwd)"
    break
  fi
done

PASS=0
WARN=0
FAIL=0

print_help() {
  cat <<'EOF'
agentic-security-assessment install.sh — prerequisite checker.

Checks agentic-dev-team presence + contract version, Python >= 3.10, and
tier-1 static-analysis tools. Prints the settings.local.json opt-out
snippet for disabling hooks.

Flags:
  --help    show this message
EOF
}

if [ "${1:-}" = "--help" ]; then print_help; exit 0; fi

section() {
  echo ""
  echo "── $* ──"
}

req() {
  local cmd="$1" tier="$2" install_hint="$3"
  if command -v "$cmd" &>/dev/null; then
    printf '  [ok]   %-14s — %s\n' "$cmd" "$tier"
    PASS=$((PASS + 1))
  else
    printf '  [FAIL] [REQUIRED] %-4s %s — %s. install: %s\n' "$cmd" "" "$tier" "$install_hint"
    FAIL=$((FAIL + 1))
  fi
}

opt() {
  local cmd="$1" tier="$2" install_hint="$3"
  if command -v "$cmd" &>/dev/null; then
    printf '  [ok]   %-14s — %s\n' "$cmd" "$tier"
    PASS=$((PASS + 1))
  else
    printf '  [warn] %-14s — %s. install: %s\n' "$cmd" "$tier" "$install_hint"
    WARN=$((WARN + 1))
  fi
}

# ── 1. agentic-dev-team presence + contract version ───────────────────────────

section "agentic-dev-team dependency"
DEV_TEAM_PATH="$REPO_ROOT/plugins/agentic-dev-team"
CONTRACT_PATH="$DEV_TEAM_PATH/knowledge/security-primitives-contract.md"

if [ -z "$REPO_ROOT" ] || [ ! -d "$DEV_TEAM_PATH" ]; then
  echo "  [FAIL] agentic-dev-team not found at expected path"
  echo "         install it first: claude plugin install agentic-dev-team@bfinster"
  FAIL=$((FAIL + 1))
elif [ ! -f "$CONTRACT_PATH" ]; then
  echo "  [FAIL] security-primitives-contract.md not found in agentic-dev-team"
  echo "         your agentic-dev-team is too old; upgrade to >= 3.4.0"
  FAIL=$((FAIL + 1))
else
  CONTRACT_VERSION=$(awk '/^---[[:space:]]*$/{c++; next} c==1 && /^version:/{sub(/^version:[[:space:]]+/,""); gsub(/["\047[:space:]]/,""); print; exit}' "$CONTRACT_PATH")
  # Simple compat: major must be 1
  MAJOR=$(echo "$CONTRACT_VERSION" | cut -d. -f1)
  if [ "$MAJOR" = "1" ]; then
    printf '  [ok]   primitives-contract %-8s — compatible with ^1.0.0\n' "$CONTRACT_VERSION"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] primitives-contract version is $CONTRACT_VERSION; need ^1.0.0"
    FAIL=$((FAIL + 1))
  fi
fi

# ── 2. Python >= 3.10 for the red-team harness ────────────────────────────────

section "python runtime"
if command -v python3 &>/dev/null; then
  PYVER=$(python3 -c 'import sys; print(".".join(str(x) for x in sys.version_info[:3]))')
  # Minor >= 10 check
  PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
  PYMINOR=$(echo "$PYVER" | cut -d. -f2)
  if [ "$PYMAJOR" -ge 3 ] && [ "$PYMINOR" -ge 10 ]; then
    printf '  [ok]   python3         — %s (red-team harness requires >= 3.10)\n' "$PYVER"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] python3 $PYVER found; red-team harness requires >= 3.10"
    FAIL=$((FAIL + 1))
  fi
else
  echo "  [FAIL] python3 not on PATH; red-team harness requires python3 >= 3.10"
  echo "         install: https://www.python.org/downloads/"
  FAIL=$((FAIL + 1))
fi

# ── 3. Tier-1 static-analysis tools, grouped by capability tier ───────────────

section "static-analysis tools — baseline (secrets / SAST / IaC / CI-CD)"
req semgrep    "SAST"                          "pip install semgrep"
req gitleaks   "secrets detection"              "brew install gitleaks"
req trivy      "IaC + supply-chain scanning"    "brew install trivy"
req hadolint   "Dockerfile linting"             "brew install hadolint"
req actionlint "GitHub Actions linting"         "brew install actionlint"

section "static-analysis tools — optional (populated by Step 3b)"
opt checkov      "IaC policy scanning"           "pip install checkov"
opt bandit       "Python SAST"                   "pip install bandit"
opt gosec        "Go SAST"                       "brew install gosec"
opt bearer       "data-flow / privacy SAST"      "brew install bearer"
opt osv-scanner  "vulnerability scanning (OSV)"  "brew install osv-scanner"
opt grype        "container vuln scanning"       "brew install grype"
opt kube-linter  "Kubernetes manifest linting"   "brew install kube-linter"
opt trufflehog   "secrets detection (SARIF v3)"  "brew install trufflehog"

section "static-analysis tools — bespoke-JSON adapter set (optional, Step 3b)"
opt detect-secrets "secrets detection"           "pip install detect-secrets"
opt depcheck       "JS dependency audit"          "npm install -g depcheck"
opt deptry         "Python dependency audit"      "pip install deptry"
opt kube-score     "Kubernetes manifest scoring"  "brew install kube-score"
opt govulncheck    "Go module CVE scanning"       "go install golang.org/x/vuln/cmd/govulncheck@latest"

section "red-team harness dependencies (optional, required for /redteam-model)"
opt pandoc       "PDF export"                      "brew install pandoc"
opt weasyprint   "PDF export (fallback)"           "pip install weasyprint"

# Python packages can't use command -v — check via import.
printf "  [info] python harness packages checked at /redteam-model invocation time;\n"
printf "         see plugins/agentic-security-assessment/harness/redteam/requirements.txt\n"

# ── 4. Hook opt-out snippet ───────────────────────────────────────────────────

section "hooks default ON"
cat <<'EOF'
  The PostToolUse auto-scan hook is registered in this plugin's settings.json.
  Default severity threshold: error only. To opt out, add to settings.local.json:

    {
      "hooks": {
        "PostToolUse": [
          { "matcher": "Edit|Write", "hooks": [] }
        ]
      }
    }

  To enable warning-level surfacing: set "verbose_hooks": true at the root
  of settings.local.json.
EOF

# ── Stale-opt-out check (post 1.0.0 rename) ──────────────────────────────────
# Warn if the user's settings.local.json still references the old plugin name.

section "checking for stale opt-out snippets from pre-1.0.0 plugin name"
for settings in "$HOME/.claude/settings.local.json" "$(pwd)/.claude/settings.local.json"; do
  if [ -f "$settings" ] && grep -q 'agentic-security-review' "$settings" 2>/dev/null; then
    echo "  [WARN] $settings references the old plugin name 'agentic-security-review'."
    echo "         Update to 'agentic-security-assessment'. See CHANGELOG 1.0.0 for the full migration."
    WARN=$((WARN + 1))
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────

section "summary"
echo "  PASS: $PASS   WARN: $WARN   FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "  Install failed. Address the [FAIL] items above and re-run."
  exit 1
fi
if [ "$WARN" -gt 0 ]; then
  echo ""
  echo "  Install succeeded with warnings. Optional tools are absent; the plugin"
  echo "  will gracefully degrade for each missing tool."
fi
echo ""
echo "  Ready. Try: /security-assessment ."
exit 0
