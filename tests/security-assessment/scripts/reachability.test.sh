#!/usr/bin/env bash
# reachability.test.sh — tests for
# plugins/security-assessment/skills/false-positive-reduction/tools/reachability.sh
#
# joern is not installed in CI, so we stub `joern-parse` / `joern-export` on
# PATH. The stubs record their args and synthesize output files, which lets us
# assert language detection, the --language flag, language-tagged cache keys,
# and the exit-code contract deterministically.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../../../plugins/security-assessment/skills/false-positive-reduction/tools/reachability.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

# --- stub bindirs ---------------------------------------------------------
# good/ : joern-parse records args + writes a non-empty CPG; joern-export emits JSON.
# fail/ : joern-parse exits 2 (build failure), joern-export never reached.
ARGS_FILE="$TMP/joern-args.txt"
GOOD_BIN="$TMP/good-bin"
FAIL_BIN="$TMP/fail-bin"
mkdir -p "$GOOD_BIN" "$FAIL_BIN"

cat >"$GOOD_BIN/joern-parse" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$ARGS_FILE"
out=""; prev=""
for a in "\$@"; do [ "\$prev" = "--output" ] && out="\$a"; prev="\$a"; done
[ -n "\$out" ] && printf 'CPG-BYTES\n' > "\$out"
exit 0
EOF
cat >"$GOOD_BIN/joern-export" <<'EOF'
#!/usr/bin/env bash
echo '{"nodes":[]}'
exit 0
EOF
cat >"$FAIL_BIN/joern-parse" <<'EOF'
#!/usr/bin/env bash
echo "joern-parse: simulated build failure" >&2
exit 2
EOF
chmod +x "$GOOD_BIN"/* "$FAIL_BIN"/*

# run_reach <extra-PATH-bindir> <repo> -> sets RC, OUT, ERR; resets ARGS_FILE
run_reach() {
  : > "$ARGS_FILE"
  local bindir="$1" repo="$2" cache="$TMP/cache.$RANDOM"
  CACHE_LAST="$cache"
  if [ -n "$bindir" ]; then
    OUT="$(PATH="$bindir:$PATH" bash "$SCRIPT" "$repo" "$cache" 2>"$TMP/err")" && RC=0 || RC=$?
  else
    OUT="$(bash "$SCRIPT" "$repo" "$cache" 2>"$TMP/err")" && RC=0 || RC=$?
  fi
  ERR="$(cat "$TMP/err")"
}

# --- fixtures: one dir per ecosystem --------------------------------------
mk() { mkdir -p "$TMP/$1"; ( cd "$TMP/$1" && shift; for f in "$@"; do mkdir -p "$(dirname "$f")"; : > "$f"; done ); }
mk csharp     ignore   src/App.csproj  Program.cs
mk node       ignore   package.json    src/index.ts
mk python     ignore   pyproject.toml  app.py
mk java       ignore   pom.xml         src/Main.java
mk go         ignore   go.mod          main.go
mk unknown    ignore   README.md       notes.txt
mk mixed      ignore   App.cs          package.json   # csharp must win (checked first)

# --- 1..5: each ecosystem maps to the right --language --------------------
assert_lang() {
  local dir="$1" lang="$2"
  run_reach "$GOOD_BIN" "$TMP/$dir"
  [ "$RC" -eq 0 ] || { fail "$dir: expected exit 0, got $RC ($ERR)"; return; }
  grep -q -- "--language $lang" "$ARGS_FILE" \
    || { fail "$dir: joern-parse not called with '--language $lang'; args: $(cat "$ARGS_FILE")"; return; }
  [ -f "$CACHE_LAST/working-tree.$lang.cpg" ] \
    || { fail "$dir: cache not keyed working-tree.$lang.cpg ($(ls "$CACHE_LAST"))"; return; }
  [ "$OUT" = "$CACHE_LAST/working-tree.$lang.cfg.json" ] \
    || { fail "$dir: stdout not the cfg.json path: $OUT"; return; }
  ok "$dir → --language $lang + cache key working-tree.$lang.cpg"
}
assert_lang csharp csharp
assert_lang node   javascript
assert_lang python python
assert_lang java   javasrc
assert_lang go     gosrc

# --- 6: unknown ecosystem → no --language flag, cache tag "auto" ----------
test_autodetect() {
  run_reach "$GOOD_BIN" "$TMP/unknown"
  [ "$RC" -eq 0 ] || { fail "unknown: expected exit 0, got $RC"; return; }
  if grep -q -- "--language" "$ARGS_FILE"; then
    fail "unknown: should NOT pass --language; args: $(cat "$ARGS_FILE")"; return
  fi
  [ -f "$CACHE_LAST/working-tree.auto.cpg" ] \
    || { fail "unknown: cache not keyed working-tree.auto.cpg ($(ls "$CACHE_LAST"))"; return; }
  ok "unknown ecosystem → autodetect (no --language), cache tag 'auto'"
}
test_autodetect

# --- 7: first match wins (csharp before javascript) -----------------------
test_first_match() {
  run_reach "$GOOD_BIN" "$TMP/mixed"
  grep -q -- "--language csharp" "$ARGS_FILE" \
    || { fail "mixed: expected csharp to win; args: $(cat "$ARGS_FILE")"; return; }
  if grep -q -- "--language javascript" "$ARGS_FILE"; then
    fail "mixed: javascript should not be selected"; return
  fi
  ok "mixed .cs + package.json → csharp wins (first match)"
}
test_first_match

# --- 8: joern absent → exit 1 (LLM fallback) ------------------------------
test_joern_absent() {
  run_reach "" "$TMP/csharp"   # no stub bindir; real env has no joern-parse
  if command -v joern-parse >/dev/null 2>&1; then
    ok "joern absent: SKIPPED (joern-parse present in env)"; return
  fi
  [ "$RC" -eq 1 ] || { fail "joern absent: expected exit 1, got $RC"; return; }
  grep -qi 'LLM fallback' <<<"$ERR" || { fail "joern absent: stderr missing LLM-fallback note: $ERR"; return; }
  ok "joern absent → exit 1 + LLM-fallback note"
}
test_joern_absent

# --- 9: malformed/failed .NET build → exit 2 + structured reason ----------
test_build_failure() {
  run_reach "$FAIL_BIN" "$TMP/csharp"
  [ "$RC" -eq 2 ] || { fail "build failure: expected exit 2, got $RC"; return; }
  grep -qi 'joern-parse failed' <<<"$ERR" \
    || { fail "build failure: stderr missing structured reason: $ERR"; return; }
  grep -qi 'language=csharp' <<<"$ERR" \
    || { fail "build failure: stderr should name the detected language: $ERR"; return; }
  ok "failed C# build → exit 2 + structured reason naming language"
}
test_build_failure

echo "=== reachability tests ==="
if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all reachability tests passed ==="
exit 0
