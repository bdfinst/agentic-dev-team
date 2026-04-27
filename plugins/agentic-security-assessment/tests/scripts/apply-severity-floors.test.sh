#!/usr/bin/env bash
# apply-severity-floors.test.sh — tests for scripts/apply-severity-floors.sh.
#
# Byte-identical regression target: running the script against the committed
# fixture (tests/scripts/fixtures/severity-floors/input-disposition-extranetapi.json)
# must produce a log file byte-identical to expected-log-extranetapi.jsonl
# (the 2026-04-24 reference run).

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../../scripts/apply-severity-floors.sh"
FIXTURES="$THIS_DIR/fixtures/severity-floors"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

# --- 1. -h prints usage, exit-code contract, exits 0 ---------------------
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

# --- 2. Missing argument → exit 3, usage to stderr -----------------------
test_missing_arg() {
  local rc err
  err="$(bash "$SCRIPT" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -eq 3 ]] || { fail "no-args expected exit 3, got $rc"; return; }
  grep -q 'usage:' <<<"$err" || { fail "no-args missing usage on stderr"; return; }
  ok "missing-arg: exit 3 + usage on stderr"
}

# --- 3. Missing disposition register → exit 2 + actionable stderr -------
test_missing_disposition() {
  local mem="$TMP/empty_mem"
  mkdir -p "$mem"
  local rc err
  err="$(bash "$SCRIPT" ivr "$mem" 2>&1 >/dev/null)" && rc=0 || rc=$?
  [[ $rc -eq 2 ]] || { fail "missing-disp expected exit 2, got $rc"; return; }
  grep -qi 'disposition-ivr.json not found' <<<"$err" \
    || { fail "stderr missing 'disposition-ivr.json not found': $err"; return; }
  ok "missing disposition: exit 2 + actionable stderr"
}

# --- 4. Byte-identical regression against 2026-04-24 reference -----------
test_byte_identical() {
  local mem="$TMP/floors_run1"
  mkdir -p "$mem"
  cp "$FIXTURES/input-disposition-extranetapi.json" "$mem/disposition-extranetapi.json"
  bash "$SCRIPT" extranetapi "$mem" || { fail "script exited non-zero on fixture"; return; }
  local expected="$FIXTURES/expected-log-extranetapi.jsonl"
  local actual="$mem/severity-floors-log-extranetapi.jsonl"
  [[ -f "$actual" ]] || { fail "log not written at $actual"; return; }
  if ! diff -u "$expected" "$actual" >"$TMP/bytediff.txt" 2>&1; then
    fail "byte-identical assertion failed; diff saved:"
    head -40 "$TMP/bytediff.txt" >&2
    return
  fi
  ok "byte-identical against 2026-04-24 reference (17 records)"
}

# --- 5. Idempotency: second run produces no new records + unchanged disp -
# Semantically grounded: asserts floor_applied is set on matched entries after
# the first run (not merely hash equality) — so serialization variance across
# Python versions cannot produce a false pass.
test_idempotent() {
  local mem="$TMP/floors_run2"
  mkdir -p "$mem"
  cp "$FIXTURES/input-disposition-extranetapi.json" "$mem/disposition-extranetapi.json"
  # First run
  bash "$SCRIPT" extranetapi "$mem" || { fail "first run failed"; return; }
  local size1
  size1="$(wc -c <"$mem/severity-floors-log-extranetapi.jsonl" | tr -d ' ')"
  # Semantic check: every logged id must have floor_applied=true in the
  # disposition register after run 1.
  python3 -c "
import json
logged_ids = {json.loads(l)['id'] for l in open('$FIXTURES/expected-log-extranetapi.jsonl')}
d = json.load(open('$mem/disposition-extranetapi.json'))
for e in d['entries']:
    if e['id'] in logged_ids:
        assert e['exploitability'].get('floor_applied') is True, \
          f'floor_applied not set on {e[\"id\"]}'
# And un-logged entries MUST NOT carry the marker.
for e in d['entries']:
    if e['id'] not in logged_ids:
        assert e['exploitability'].get('floor_applied') is not True, \
          f'floor_applied unexpectedly set on un-logged {e[\"id\"]}'
" || { fail "floor_applied semantic check failed after run 1"; return; }
  # Second run
  bash "$SCRIPT" extranetapi "$mem" || { fail "second run failed"; return; }
  local size2
  size2="$(wc -c <"$mem/severity-floors-log-extranetapi.jsonl" | tr -d ' ')"
  [[ "$size1" == "$size2" ]] \
    || { fail "log grew on second run: $size1 → $size2"; return; }
  # Semantic: scores of previously-floored entries unchanged.
  python3 -c "
import json
logged = {json.loads(l)['id']: json.loads(l) for l in open('$FIXTURES/expected-log-extranetapi.jsonl')}
d = json.load(open('$mem/disposition-extranetapi.json'))
for e in d['entries']:
    if e['id'] in logged:
        expected_final = logged[e['id']]['final_score']
        actual = e['exploitability']['score']
        assert actual == expected_final, f'score drifted on {e[\"id\"]}: {actual} != {expected_final}'
" || { fail "disposition score drifted on second run"; return; }
  ok "idempotent: floor_applied marker set + no new records on re-run + scores stable"
}

# --- 6. Entry with "suppressed to" phrase is NOT logged ------------------
test_suppression_phrase() {
  local mem="$TMP/floors_suppress"
  mkdir -p "$mem"
  cat >"$mem/disposition-synth.json" <<'JSON'
{
  "schema_version": "disposition-v1.1.0",
  "target_slug": "synth",
  "entries": [
    {"id": "sec-mid-1", "verdict": "likely_true_positive",
     "exploitability": {"score": 4,
       "rationale": "info-leak-unauth floor=5 suppressed to 4: X-Request-Id is a conventional trace-correlation header."},
     "reachability": "reached"}
  ]
}
JSON
  bash "$SCRIPT" synth "$mem" || { fail "script failed on synth input"; return; }
  local log="$mem/severity-floors-log-synth.jsonl"
  # Either no log file or empty log file is acceptable.
  if [[ -s "$log" ]]; then
    fail "expected no log records for suppressed entry; got:"
    cat "$log" >&2
    return
  fi
  # Disposition file MUST still exist and be valid JSON (atomic mv ran).
  [[ -f "$mem/disposition-synth.json" ]] \
    || { fail "disposition file missing after run"; return; }
  [[ ! -f "$mem/disposition-synth.json.tmp" ]] \
    || { fail "stale .tmp file left behind: atomic mv did not run"; return; }
  python3 -c "
import json
d = json.load(open('$mem/disposition-synth.json'))
e = d['entries'][0]
assert e['exploitability']['score'] == 4, f\"score mutated: {e['exploitability']['score']}\"
assert not e['exploitability'].get('floor_applied'), 'floor_applied set for suppressed entry'
" || { fail "suppressed entry was mutated"; return; }
  ok "'suppressed to' entry: not logged, not mutated, atomic rewrite still ran"
}

# --- 7. Un-matched findings emit no record -------------------------------
test_unmatched_emits_nothing() {
  local mem="$TMP/floors_unmatched"
  mkdir -p "$mem"
  cat >"$mem/disposition-synth.json" <<'JSON'
{
  "schema_version": "disposition-v1.1.0",
  "target_slug": "synth",
  "entries": [
    {"id": "sec-noisy-1", "verdict": "likely_false_positive",
     "exploitability": {"score": 2, "rationale": "Test-only code, no floor applies."},
     "reachability": "reached"},
    {"id": "sec-off-list-1", "verdict": "true_positive",
     "exploitability": {"score": 6, "rationale": "unknown-class floor=8: not in allow-list."},
     "reachability": "reached"}
  ]
}
JSON
  bash "$SCRIPT" synth "$mem" || { fail "script failed"; return; }
  local log="$mem/severity-floors-log-synth.jsonl"
  if [[ -s "$log" ]]; then
    fail "expected empty log for un-matched findings; got:"
    cat "$log" >&2
    return
  fi
  ok "un-matched findings (no pattern + off-list class) emit no record"
}

# --- 8. Every log record cites a floor_class + schema fields ------------
test_log_record_schema() {
  local mem="$TMP/floors_schema"
  mkdir -p "$mem"
  cp "$FIXTURES/input-disposition-extranetapi.json" "$mem/disposition-extranetapi.json"
  bash "$SCRIPT" extranetapi "$mem" || { fail "script failed"; return; }
  local log="$mem/severity-floors-log-extranetapi.jsonl"
  python3 -c "
import json, sys
rows = [json.loads(l) for l in open('$log')]
required = {'id','floor_class','floor','original_score','final_score'}
for r in rows:
    missing = required - set(r.keys())
    assert not missing, f'record missing fields {missing}: {r}'
    extra = set(r.keys()) - required
    assert not extra, f'record has unexpected fields {extra}: {r}'
    assert isinstance(r['floor'], int), f'floor not int: {r}'
    assert isinstance(r['original_score'], int), f'original_score not int: {r}'
    assert isinstance(r['final_score'], int), f'final_score not int: {r}'
    assert r['final_score'] >= r['original_score'], f'final < original: {r}'
    assert r['final_score'] >= r['floor'], f'final < floor: {r}'
" || { fail "log schema validation failed"; return; }
  ok "log records carry {id,floor_class,floor,original_score,final_score}"
}

# --- 9. Non-raising branch: original_score > floor → final == original ---
# Exercises max() in the non-raising direction: the score is already above
# the floor, so the script logs the match (per log-every-match semantics)
# but does not change the score.
test_original_exceeds_floor() {
  local mem="$TMP/floors_noraise"
  mkdir -p "$mem"
  cat >"$mem/disposition-synth.json" <<'JSON'
{
  "schema_version": "disposition-v1.1.0",
  "target_slug": "synth",
  "entries": [
    {"id": "sec-already-high", "verdict": "true_positive",
     "exploitability": {"score": 9, "rationale": "tls-disabled floor=7 — score already at 9 from reachability + exposure."},
     "reachability": "reached"}
  ]
}
JSON
  bash "$SCRIPT" synth "$mem" || { fail "script failed"; return; }
  local log="$mem/severity-floors-log-synth.jsonl"
  [[ -f "$log" && -s "$log" ]] || { fail "expected one log record, got empty/missing log"; return; }
  python3 -c "
import json
rows = [json.loads(l) for l in open('$log')]
assert len(rows) == 1, f'expected 1 record, got {len(rows)}'
r = rows[0]
assert r['id'] == 'sec-already-high'
assert r['floor_class'] == 'tls-disabled'
assert r['floor'] == 7
assert r['original_score'] == 9
assert r['final_score'] == 9, f'final drifted: {r[\"final_score\"]}'
d = json.load(open('$mem/disposition-synth.json'))
assert d['entries'][0]['exploitability']['score'] == 9
assert d['entries'][0]['exploitability']['floor_applied'] is True
" || { fail "non-raise branch assertions failed"; return; }
  ok "non-raising branch: original=9 floor=7 → final=9 (logged, score unchanged)"
}

echo "=== apply-severity-floors tests ==="
test_help
test_missing_arg
test_missing_disposition
test_byte_identical
test_idempotent
test_suppression_phrase
test_unmatched_emits_nothing
test_log_record_schema
test_original_exceeds_floor

if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all apply-severity-floors tests passed ==="
exit 0
