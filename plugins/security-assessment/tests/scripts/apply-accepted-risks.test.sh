#!/usr/bin/env bash
# apply-accepted-risks.test.sh — tests for scripts/apply-accepted-risks.sh.
#
# Fixtures are built inline; the ACCEPTED-RISKS.md format is a fenced
# ```json code block (first one wins) so that jq can parse without a
# pyyaml dependency.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../../scripts/apply-accepted-risks.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

# --- Helpers -------------------------------------------------------------

# Build a <target-dir> + <memory-dir> pair. Sets globals TGT and MEM.
build_setup() {
  local tag="$1"
  TGT="$TMP/$tag/target"
  MEM="$TMP/$tag/mem"
  mkdir -p "$TGT" "$MEM"
}

# Write an ACCEPTED-RISKS.md with the given JSON body wrapped in a fenced
# ```json block plus some prose surrounding it.
write_accepted_risks() {
  local path="$1"
  local json_body="$2"
  cat >"$path" <<MARK
# ACCEPTED-RISKS

Suppression entries for this repo. The \`json\` block below is parsed by
\`apply-accepted-risks.sh\`; free prose is ignored.

\`\`\`json
$json_body
\`\`\`

Approvals history, justifications, etc. can live as prose here.
MARK
}

# Write a findings-<slug>.jsonl with the given list of {rule_id, source_ref} pairs.
# Each line in the input has form "rule_id|source_ref".
write_findings() {
  local path="$1"; shift
  : >"$path"
  local pair rid ref
  for pair in "$@"; do
    rid="${pair%%|*}"
    ref="${pair#*|}"
    printf '{"rule_id":"%s","source_ref":"%s"}\n' "$rid" "$ref" >> "$path"
  done
}

# --- 1. -h prints usage + exit-code contract to stdout -------------------
test_help() {
  local out err rc
  out="$(bash "$SCRIPT" -h 2>"$TMP/help_err")" && rc=0 || rc=$?
  err="$(cat "$TMP/help_err")"
  [[ $rc -eq 0 ]] || { fail "-h exited non-zero"; return; }
  [[ -z "$err" ]] || { fail "-h wrote to stderr: $err"; return; }
  grep -q 'usage:' <<<"$out" || { fail "-h missing 'usage:'"; return; }
  for code in 0 1 2 3; do
    grep -q -E "(^|[^0-9])${code}([^0-9]|$)" <<<"$out" \
      || { fail "-h missing exit code $code"; return; }
  done
  ok "-h prints usage and exit-code contract"
}

# --- 2. Missing arguments → exit 3 + usage on stderr --------------------
test_missing_arg() {
  local rc err
  err="$(bash "$SCRIPT" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -eq 3 ]] || { fail "no-args expected exit 3, got $rc"; return; }
  grep -q 'usage:' <<<"$err" || { fail "no-args missing usage on stderr"; return; }
  ok "missing-arg: exit 3 + usage on stderr"
}

# --- 3. No ACCEPTED-RISKS.md → exit 0, findings unchanged, no log -------
test_no_accepted_risks_file() {
  build_setup no_arf
  write_findings "$MEM/findings-x.jsonl" "rule.a|src/a.cs" "rule.b|src/b.cs"
  local before_hash
  before_hash="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  local rc
  bash "$SCRIPT" "$TGT" x "$MEM" && rc=0 || rc=$?
  [[ $rc -eq 0 ]] || { fail "expected exit 0, got $rc"; return; }
  local after_hash
  after_hash="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  [[ "$before_hash" == "$after_hash" ]] \
    || { fail "findings file changed"; return; }
  [[ ! -e "$MEM/accepted-risks-x.jsonl" ]] \
    || { fail "log unexpectedly written: $MEM/accepted-risks-x.jsonl"; return; }
  ok "no ACCEPTED-RISKS.md: exit 0, findings unchanged, no log"
}

# --- 4. Exact source_ref match: finding suppressed + log record ----------
test_exact_match() {
  build_setup exact
  local future="2030-01-01"
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<JSON
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/Legacy/Foo.cs","reason":"legacy; removal planned","expires":"$future"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/Legacy/Foo.cs" \
    "rule.b|src/Other.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script exited non-zero"; return; }
  # Findings file should have only the non-suppressed one left.
  local count
  count="$(wc -l <"$MEM/findings-x.jsonl" | tr -d ' ')"
  [[ "$count" == "1" ]] || { fail "expected 1 finding left, got $count"; return; }
  grep -q '"rule_id":"rule.b"' "$MEM/findings-x.jsonl" \
    || { fail "rule.b finding should have survived"; return; }
  # Log: one record citing rule.a.
  [[ -f "$MEM/accepted-risks-x.jsonl" ]] || { fail "log missing"; return; }
  count="$(wc -l <"$MEM/accepted-risks-x.jsonl" | tr -d ' ')"
  [[ "$count" == "1" ]] || { fail "expected 1 log record, got $count"; return; }
  python3 -c "
import json, re
r = json.loads(open('$MEM/accepted-risks-x.jsonl').read().strip())
assert r['status'] == 'suppressed', r
assert r['rule_id'] == 'rule.a', r
assert r['source_ref'] == 'src/Legacy/Foo.cs', r
assert r['reason'].startswith('legacy'), r
assert r['expires'] == '$future', r
iso = r.get('iso', '')
assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', iso), f'iso malformed: {iso!r}'
" || { fail "log record schema mismatch"; return; }
  ok "exact match: suppressed + logged with status + iso"
}

# --- 5. Glob match: multiple findings suppressed + one log record each --
test_glob_match() {
  build_setup glob
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<JSON
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/**/*.cs","reason":"blanket exception","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/One.cs" \
    "rule.a|src/nested/Two.cs" \
    "rule.a|other/Three.cs" \
    "rule.b|src/Four.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script exited non-zero"; return; }
  local remaining
  remaining="$(wc -l <"$MEM/findings-x.jsonl" | tr -d ' ')"
  [[ "$remaining" == "2" ]] \
    || { fail "expected 2 findings remaining (other/Three.cs + rule.b), got $remaining"; return; }
  grep -q '"source_ref":"other/Three.cs"' "$MEM/findings-x.jsonl" \
    || { fail "other/Three.cs should have survived (outside src/)"; return; }
  grep -q '"rule_id":"rule.b"' "$MEM/findings-x.jsonl" \
    || { fail "rule.b should have survived"; return; }
  local logs
  logs="$(wc -l <"$MEM/accepted-risks-x.jsonl" | tr -d ' ')"
  [[ "$logs" == "2" ]] || { fail "expected 2 log records, got $logs"; return; }
  ok "glob match: ** recurses, * does not cross /"
}

# --- 6. Expired entry: logged with status:expired, finding retained ------
test_expired_entry() {
  build_setup expired
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/Old.cs","reason":"lapsed","expires":"2020-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" "rule.a|src/Old.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script exited non-zero"; return; }
  # Finding must survive.
  grep -q '"source_ref":"src/Old.cs"' "$MEM/findings-x.jsonl" \
    || { fail "expired entry must NOT suppress — finding should have survived"; return; }
  # Log must contain a status:"expired" record.
  python3 -c "
import json
rows = [json.loads(l) for l in open('$MEM/accepted-risks-x.jsonl')]
assert len(rows) == 1, f'expected 1 log record, got {len(rows)}'
r = rows[0]
assert r.get('status') == 'expired', f'expected status:expired, got {r}'
assert r.get('rule_id') == 'rule.a'
assert r.get('expires') == '2020-01-01'
" || { fail "expired-entry log schema mismatch"; return; }
  ok "expired entry: logged with status:expired, finding retained"
}

# --- 7. Malformed JSON → exit 3 + clear stderr, findings unchanged ------
test_malformed_json() {
  build_setup malformed
  cat >"$TGT/ACCEPTED-RISKS.md" <<'MARK'
# ACCEPTED-RISKS

```json
{ this is not valid json
```
MARK
  write_findings "$MEM/findings-x.jsonl" "rule.a|src/a.cs"
  local before_hash
  before_hash="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  local rc err
  err="$(bash "$SCRIPT" "$TGT" x "$MEM" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -eq 3 ]] || { fail "expected exit 3, got $rc"; return; }
  grep -q 'ACCEPTED-RISKS.md parse error' <<<"$err" \
    || { fail "stderr missing 'parse error': $err"; return; }
  local after_hash
  after_hash="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  [[ "$before_hash" == "$after_hash" ]] \
    || { fail "findings file changed after malformed input"; return; }
  [[ ! -e "$MEM/accepted-risks-x.jsonl" ]] \
    || { fail "log unexpectedly written"; return; }
  ok "malformed JSON: exit 3 + parse error on stderr + findings unchanged"
}

# --- 8. Missing required field → exit 3 ---------------------------------
test_missing_required_field() {
  build_setup missing_field
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/a.cs","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" "rule.a|src/a.cs"
  local rc err
  err="$(bash "$SCRIPT" "$TGT" x "$MEM" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -eq 3 ]] || { fail "expected exit 3, got $rc"; return; }
  grep -qi 'missing required field\|parse error' <<<"$err" \
    || { fail "stderr missing field-validation language: $err"; return; }
  ok "missing required field (reason): exit 3"
}

# --- 9. Atomic rewrite: .tmp does not remain after successful run -------
test_atomic_rewrite_cleanup() {
  build_setup atomic
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/a.cs","reason":"x","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" "rule.a|src/a.cs" "rule.b|src/b.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script failed"; return; }
  [[ ! -e "$MEM/findings-x.jsonl.tmp" ]] \
    || { fail "stale findings-x.jsonl.tmp left behind"; return; }
  # And findings file is still valid JSONL.
  python3 -c "
import json
for line in open('$MEM/findings-x.jsonl'):
    json.loads(line)
" || { fail "findings file not valid JSONL after run"; return; }
  ok "atomic rewrite: .tmp cleaned up, findings file valid"
}

# --- 10. Idempotency: re-run produces byte-identical findings + log ----
test_idempotent() {
  build_setup idem
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/**/*.cs","reason":"bulk","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/One.cs" "rule.a|src/Two.cs" "rule.b|src/Keep.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "first run failed"; return; }
  local findings_hash_1 log_hash_1
  findings_hash_1="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  log_hash_1="$(shasum -a 256 "$MEM/accepted-risks-x.jsonl" | awk '{print $1}')"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "second run failed"; return; }
  local findings_hash_2 log_hash_2
  findings_hash_2="$(shasum -a 256 "$MEM/findings-x.jsonl" | awk '{print $1}')"
  log_hash_2="$(shasum -a 256 "$MEM/accepted-risks-x.jsonl" | awk '{print $1}')"
  [[ "$findings_hash_1" == "$findings_hash_2" ]] \
    || { fail "findings hash drifted on second run"; return; }
  [[ "$log_hash_1" == "$log_hash_2" ]] \
    || { fail "log hash drifted on second run"; return; }
  ok "idempotent: findings + log byte-identical across re-runs"
}

# --- Glob dot in source_ref_glob is literal ------------------------------
# Ensures `.` in the glob is escaped; a finding whose source_ref differs
# only by substituting the dot with any other character must NOT match.
test_dot_in_glob_is_literal() {
  build_setup dot_literal
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/Foo.cs","reason":"literal","expires":"2030-01-01"}
]}
JSON
)"
  # Both findings have rule_id rule.a. One matches the glob exactly; the
  # other replaces the dot with X — it must survive.
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/Foo.cs" \
    "rule.a|src/FooXcs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script failed"; return; }
  grep -qF '"source_ref":"src/FooXcs"' "$MEM/findings-x.jsonl" \
    || { fail "src/FooXcs should have survived (dot must be literal)"; return; }
  if grep -qF '"source_ref":"src/Foo.cs"' "$MEM/findings-x.jsonl"; then
    fail "src/Foo.cs should have been suppressed"
    return
  fi
  ok "dot-in-glob: literal match only; '.' is not regex wildcard"
}

# --- Question-mark glob: single non-/ char -------------------------------
test_question_mark_glob() {
  build_setup qmark
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/?.cs","reason":"single-char","expires":"2030-01-01"}
]}
JSON
)"
  # A matches (single char); AB must survive (two chars); a/B must survive
  # (? does not match /).
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/A.cs" \
    "rule.a|src/AB.cs" \
    "rule.a|src/a/B.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script failed"; return; }
  if grep -q '"source_ref":"src/A.cs"' "$MEM/findings-x.jsonl"; then
    fail "src/A.cs should have been suppressed by single-char '?'"; return
  fi
  grep -q '"source_ref":"src/AB.cs"' "$MEM/findings-x.jsonl" \
    || { fail "src/AB.cs should have survived (2 chars, ? matches only 1)"; return; }
  grep -q '"source_ref":"src/a/B.cs"' "$MEM/findings-x.jsonl" \
    || { fail "src/a/B.cs should have survived (? does not match /)"; return; }
  ok "?-glob: single non-/ char; AB and a/B survive"
}

# --- Mixed active + expired entries for the same rule_id -----------------
test_mixed_active_and_expired() {
  build_setup mixed
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/Old/*.cs","reason":"old","expires":"2020-01-01"},
  {"rule_id":"rule.a","source_ref_glob":"src/New/*.cs","reason":"still live","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" \
    "rule.a|src/Old/A.cs" \
    "rule.a|src/New/B.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script failed"; return; }
  # Old/A.cs must survive (expired entry does not suppress).
  grep -q '"source_ref":"src/Old/A.cs"' "$MEM/findings-x.jsonl" \
    || { fail "src/Old/A.cs should have survived (expired entry)"; return; }
  # New/B.cs must be suppressed.
  if grep -q '"source_ref":"src/New/B.cs"' "$MEM/findings-x.jsonl"; then
    fail "src/New/B.cs should have been suppressed by active entry"; return
  fi
  # Log: one status:expired + one status:suppressed.
  python3 -c "
import json
rows = [json.loads(l) for l in open('$MEM/accepted-risks-x.jsonl')]
statuses = sorted(r['status'] for r in rows)
assert statuses == ['expired', 'suppressed'], f'expected [expired, suppressed], got {statuses}'
# The suppressed one must cite New/B; the expired one must cite the Old glob.
suppressed = [r for r in rows if r['status']=='suppressed'][0]
expired = [r for r in rows if r['status']=='expired'][0]
assert suppressed['source_ref'] == 'src/New/B.cs'
assert expired['source_ref_glob'] == 'src/Old/*.cs'
" || { fail "mixed-entry log assertions failed"; return; }
  ok "mixed active+expired for same rule_id: active suppresses, expired logs"
}

# --- 11. Un-matched rule_id: not suppressed, not logged ------------------
test_rule_id_mismatch() {
  build_setup mismatch
  write_accepted_risks "$TGT/ACCEPTED-RISKS.md" "$(cat <<'JSON'
{"accepted_risks":[
  {"rule_id":"rule.a","source_ref_glob":"src/*.cs","reason":"narrow","expires":"2030-01-01"}
]}
JSON
)"
  write_findings "$MEM/findings-x.jsonl" "rule.OTHER|src/a.cs"
  bash "$SCRIPT" "$TGT" x "$MEM" || { fail "script failed"; return; }
  grep -q '"rule_id":"rule.OTHER"' "$MEM/findings-x.jsonl" \
    || { fail "rule.OTHER should have survived"; return; }
  [[ ! -s "$MEM/accepted-risks-x.jsonl" ]] \
    || { fail "expected empty log for rule_id mismatch"; return; }
  ok "rule_id mismatch: not suppressed, not logged"
}

echo "=== apply-accepted-risks tests ==="
test_help
test_missing_arg
test_no_accepted_risks_file
test_exact_match
test_glob_match
test_expired_entry
test_malformed_json
test_missing_required_field
test_atomic_rewrite_cleanup
test_idempotent
test_dot_in_glob_is_literal
test_question_mark_glob
test_mixed_active_and_expired
test_rule_id_mismatch

if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all apply-accepted-risks tests passed ==="
exit 0
