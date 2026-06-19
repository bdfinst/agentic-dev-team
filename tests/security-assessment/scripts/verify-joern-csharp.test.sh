#!/usr/bin/env bash
# verify-joern-csharp.test.sh — tests for
# plugins/security-assessment/scripts/verify-joern-csharp.sh
#
# joern is absent in CI, so we stub joern-parse on PATH to exercise the three
# verification outcomes (built / absent / empty-or-failed) deterministically.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$THIS_DIR/../../../plugins/security-assessment"
SCRIPT="$PLUGIN/scripts/verify-joern-csharp.sh"
FIXTURE_DIR="$PLUGIN/knowledge/fixtures/joern-dotnet"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

ARGS_FILE="$TMP/args.txt"
GOOD="$TMP/good"; EMPTY="$TMP/empty"; FAILBIN="$TMP/failbin"
mkdir -p "$GOOD" "$EMPTY" "$FAILBIN"

# good: writes a non-empty CPG at --output
cat >"$GOOD/joern-parse" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$ARGS_FILE"
out=""; prev=""; for a in "\$@"; do [ "\$prev" = "--output" ] && out="\$a"; prev="\$a"; done
[ -n "\$out" ] && printf 'CPG-BYTES\n' > "\$out"
exit 0
EOF
# empty: creates an empty CPG at --output
cat >"$EMPTY/joern-parse" <<'EOF'
#!/usr/bin/env bash
out=""; prev=""; for a in "$@"; do [ "$prev" = "--output" ] && out="$a"; prev="$a"; done
[ -n "$out" ] && : > "$out"
exit 0
EOF
# failbin: joern-parse exits non-zero
cat >"$FAILBIN/joern-parse" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$GOOD/joern-parse" "$EMPTY/joern-parse" "$FAILBIN/joern-parse"

run() { # run <bindir-or-empty> [args...]
  : > "$ARGS_FILE"
  local bindir="$1"; shift
  if [ -n "$bindir" ]; then
    OUT="$(PATH="$bindir:$PATH" bash "$SCRIPT" "$@" 2>"$TMP/err")" && RC=0 || RC=$?
  else
    OUT="$(bash "$SCRIPT" "$@" 2>"$TMP/err")" && RC=0 || RC=$?
  fi
  ERR="$(cat "$TMP/err")"
}

# --- 1: joern present + non-empty CPG (default fixture) → exit 0 -----------
test_built() {
  run "$GOOD"   # no fixture arg → exercises default-fixture resolution
  [ "$RC" -eq 0 ] || { fail "built: expected exit 0, got $RC ($ERR)"; return; }
  grep -q -- '--language csharp' "$ARGS_FILE" \
    || { fail "built: did not invoke joern with --language csharp: $(cat "$ARGS_FILE")"; return; }
  grep -qi 'ok' <<<"$OUT" || { fail "built: stdout missing [ok] line: $OUT"; return; }
  ok "joern present + non-empty CPG → exit 0, --language csharp, [ok]"
}
test_built

# --- 2: joern absent → exit 1 + actionable LLM-fallback warning -----------
test_absent() {
  run ""   # real CI env: no joern-parse
  if command -v joern-parse >/dev/null 2>&1; then
    ok "absent: SKIPPED (joern-parse present in env)"; return
  fi
  [ "$RC" -eq 1 ] || { fail "absent: expected exit 1, got $RC"; return; }
  grep -qi 'LLM-fallback' <<<"$ERR" || { fail "absent: missing LLM-fallback warning: $ERR"; return; }
  grep -q 'docs.joern.io' <<<"$ERR" || { fail "absent: missing joern install docs link: $ERR"; return; }
  ok "joern absent → exit 1 + LLM-fallback warning + docs link"
}
test_absent

# --- 3: joern present but empty CPG → exit 2 ------------------------------
test_empty() {
  run "$EMPTY"
  [ "$RC" -eq 2 ] || { fail "empty: expected exit 2, got $RC"; return; }
  grep -qi 'empty' <<<"$ERR" || { fail "empty: stderr should explain empty CPG: $ERR"; return; }
  ok "joern present + empty CPG → exit 2"
}
test_empty

# --- 4: joern-parse fails → exit 2 ----------------------------------------
test_failbuild() {
  run "$FAILBIN"
  [ "$RC" -eq 2 ] || { fail "failbuild: expected exit 2, got $RC"; return; }
  ok "joern-parse non-zero → exit 2"
}
test_failbuild

# --- 5: committed fixture is a .cs source→sink chain ----------------------
test_fixture_present() {
  local cs
  cs="$(find "$FIXTURE_DIR" -name '*.cs' -type f 2>/dev/null | head -n1)"
  [ -n "$cs" ] || { fail "no .cs fixture under $FIXTURE_DIR"; return; }
  # source: HTTP input; sink: SQL command built by string concatenation.
  grep -qi 'HttpGet\|FromQuery' "$cs" || { fail "fixture missing HTTP input source"; return; }
  grep -qi 'SqlCommand\|SELECT .* FROM' "$cs" || { fail "fixture missing SQL sink"; return; }
  grep -q '+ name' "$cs" || { fail "fixture missing string-concat of user input"; return; }
  ok "fixture .cs has HTTP-input → string-concat → SQL-command chain"
}
test_fixture_present

echo "=== verify-joern-csharp tests ==="
if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all verify-joern-csharp tests passed ==="
exit 0
