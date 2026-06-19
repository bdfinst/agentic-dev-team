#!/usr/bin/env bash
# install-joern-wiring.test.sh — verify the install scripts wire in the joern
# C# reachability check (issue #60).
#
# install.sh is runnable on Linux/CI (it only checks presence), so we exercise
# its joern section behaviorally with a stubbed joern-parse. install-macos.sh
# refuses to run off Darwin, so it is checked structurally.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$THIS_DIR/../../../plugins/security-assessment"
INSTALL="$PLUGIN/install.sh"
INSTALL_MACOS="$PLUGIN/install-macos.sh"
VERIFY="$PLUGIN/scripts/verify-joern-csharp.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

STUB="$TMP/stub"
mkdir -p "$STUB"
cat >"$STUB/joern-parse" <<'EOF'
#!/usr/bin/env bash
out=""; prev=""; for a in "$@"; do [ "$prev" = "--output" ] && out="$a"; prev="$a"; done
[ -n "$out" ] && printf 'CPG-BYTES\n' > "$out"
exit 0
EOF
chmod +x "$STUB/joern-parse"

# install.sh accumulates checks and exits 1 when tier-1 tools are missing (as
# in CI). We ignore its overall exit code and inspect only the joern section.

# --- 1: joern present → install.sh reports the C# CPG path as live --------
test_install_joern_present() {
  local out
  out="$(PATH="$STUB:$PATH" bash "$INSTALL" 2>&1 || true)"
  grep -qi 'joern' <<<"$out" || { fail "install.sh has no joern section"; return; }
  grep -qi 'non-empty C# CPG\|joern-cpg' <<<"$out" \
    || { fail "install.sh did not report the joern C# path as live: $(grep -i joern <<<"$out")"; return; }
  ok "install.sh + joern present → reports C# joern-cpg path live"
}
test_install_joern_present

# --- 2: joern absent → WARN with actionable LLM-fallback note, never FAIL --
test_install_joern_absent() {
  if command -v joern-parse >/dev/null 2>&1; then
    ok "install.sh joern-absent: SKIPPED (joern present in env)"; return
  fi
  local out
  out="$(bash "$INSTALL" 2>&1 || true)"
  grep -qi 'LLM-fallback' <<<"$out" || { fail "install.sh absent: missing LLM-fallback warning"; return; }
  grep -q 'docs.joern.io' <<<"$out" || { fail "install.sh absent: missing docs link"; return; }
  # Absence must be WARN, not a hard failure: no [FAIL] line should mention joern.
  if grep -i 'joern' <<<"$out" | grep -q '\[FAIL\]'; then
    fail "install.sh absent: joern absence produced a [FAIL] (should be [warn])"; return
  fi
  ok "install.sh + joern absent → [warn] LLM-fallback + docs link, no [FAIL]"
}
test_install_joern_absent

# --- 3: install.sh documents the minimum tested joern version -------------
test_min_version_documented() {
  grep -q '2\.0\.0' "$INSTALL" || { fail "install.sh header missing min joern version 2.0.0"; return; }
  grep -q '2\.0\.0' "$VERIFY"  || { fail "verify-joern-csharp.sh missing min joern version 2.0.0"; return; }
  ok "min tested joern version (2.0.0) documented in install.sh + verify helper"
}
test_min_version_documented

# --- 4: install-macos.sh structural wiring --------------------------------
test_macos_structure() {
  grep -q 'verify-joern-csharp.sh' "$INSTALL_MACOS" || { fail "install-macos.sh does not call verify-joern-csharp.sh"; return; }
  grep -qi 'joern' "$INSTALL_MACOS"        || { fail "install-macos.sh has no joern section"; return; }
  grep -qi 'dotnetastgen' "$INSTALL_MACOS" || { fail "install-macos.sh does not install the C# frontend (dotnetastgen)"; return; }
  grep -q 'docs.joern.io' "$INSTALL_MACOS" || { fail "install-macos.sh missing joern docs link"; return; }
  grep -q '2\.0\.0' "$INSTALL_MACOS"       || { fail "install-macos.sh missing min joern version 2.0.0"; return; }
  grep -qi 'LLM-fallback' "$INSTALL_MACOS" || { fail "install-macos.sh missing LLM-fallback warning"; return; }
  # joern must not be force-added to the fatal FAILED[] array.
  if grep -E 'FAILED\+=\(.*joern' "$INSTALL_MACOS" >/dev/null; then
    fail "install-macos.sh adds joern to the fatal FAILED[] array (must stay optional)"; return
  fi
  ok "install-macos.sh wires joern + dotnetastgen + verify + docs (non-fatal)"
}
test_macos_structure

# --- 5: verify helper is shipped + executable -----------------------------
test_verify_shipped() {
  [ -x "$VERIFY" ] || { fail "verify-joern-csharp.sh missing or not executable"; return; }
  ok "verify-joern-csharp.sh shipped and executable"
}
test_verify_shipped

echo "=== install joern wiring tests ==="
if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all install joern wiring tests passed ==="
exit 0
