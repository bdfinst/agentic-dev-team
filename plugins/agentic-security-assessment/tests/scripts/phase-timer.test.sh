#!/usr/bin/env bash
# phase-timer.test.sh — tests for scripts/phase-timer.sh.
#
# Runs seven test cases; exits 0 only if all pass.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$THIS_DIR/../../scripts/phase-timer.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
fail() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
ok()   { echo "  PASS: $*"; }

# --- 1. -h prints usage + exit-code contract to stdout (not stderr), exits 0 ---
test_help() {
  local out err rc
  # Capture stdout and stderr separately so we catch regressions that
  # accidentally route usage to stderr.
  out="$(bash "$SCRIPT" -h 2>"$TMP/help_stderr")" && rc=0 || rc=$?
  err="$(cat "$TMP/help_stderr")"
  [[ $rc -eq 0 ]] || { fail "-h exited non-zero"; return; }
  [[ -z "$err" ]] || { fail "-h wrote to stderr (expected empty): $err"; return; }
  grep -q 'usage:' <<<"$out" || { fail "-h stdout missing 'usage:'"; return; }
  grep -qi 'exit' <<<"$out" || { fail "-h stdout missing exit-code contract"; return; }
  # Contract values 0, 1, 2, 3 must all be mentioned.
  for code in 0 1 2 3; do
    grep -q -E "(^|[^0-9])${code}([^0-9]|$)" <<<"$out" || { fail "-h missing exit code $code"; return; }
  done
  ok "-h prints usage and exit-code contract to stdout"
}

# --- 2. Missing arguments → non-zero exit, usage to stderr ----------------
test_missing_args() {
  local rc err
  err="$(bash "$SCRIPT" 2>&1 >/dev/null)" && rc=0 || rc=$?
  if [[ $rc -eq 0 ]]; then fail "no-args exited 0; expected non-zero"; return; fi
  grep -q 'usage:' <<<"$err" || { fail "no-args missing usage on stderr"; return; }
  ok "missing-args: non-zero exit + usage on stderr"
}

# --- 3. start+end round-trip writes 2 JSONL records with required fields --
test_round_trip() {
  local mem="$TMP/mem1"
  mkdir -p "$mem"
  bash "$SCRIPT" start phase-1-tool-pass ivr "$mem" || { fail "start exited non-zero"; return; }
  bash "$SCRIPT" end   phase-1-tool-pass ivr "$mem" || { fail "end exited non-zero"; return; }
  local file="$mem/phase-timings-ivr.jsonl"
  [[ -f "$file" ]] || { fail "expected $file to exist"; return; }
  local count
  count="$(wc -l <"$file" | tr -d ' ')"
  [[ "$count" == "2" ]] || { fail "expected 2 records, got $count"; return; }
  # Each record must be valid JSON and carry required fields with matching phase/slug.
  while IFS= read -r line; do
    for field in event phase slug epoch_ms iso pid; do
      echo "$line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert '$field' in d" 2>/dev/null \
        || { fail "record missing field $field: $line"; return; }
    done
    # phase + slug match expectations
    echo "$line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert d['phase']=='phase-1-tool-pass' and d['slug']=='ivr'" 2>/dev/null \
      || { fail "phase/slug mismatch in record: $line"; return; }
  done < "$file"
  # Events: one start, one end
  grep -q '"event": *"start"' "$file" || { fail "no start event"; return; }
  grep -q '"event": *"end"'   "$file" || { fail "no end event";   return; }
  ok "start+end round-trip produces 2 well-formed records"
}

# --- 4. Default memory-dir = ./memory -------------------------------------
test_default_memory_dir() {
  local work="$TMP/work1"
  mkdir -p "$work"
  (
    cd "$work"
    bash "$SCRIPT" start phase-0-recon ivr >/dev/null 2>&1 || exit 99
  ) || { fail "start exited non-zero under default-memdir"; return; }
  [[ -f "$work/memory/phase-timings-ivr.jsonl" ]] \
    || { fail "expected default ./memory/phase-timings-ivr.jsonl at $work/memory/"; return; }
  ok "default memory-dir resolves to ./memory"
}

# --- 5. ISO-8601 millisecond precision regex ------------------------------
test_iso_format() {
  local mem="$TMP/mem2"
  mkdir -p "$mem"
  bash "$SCRIPT" start p s "$mem" >/dev/null || { fail "start failed"; return; }
  local iso
  iso="$(python3 -c 'import json,sys;print(json.loads(open(sys.argv[1]).readline())["iso"])' "$mem/phase-timings-s.jsonl")"
  # Expect e.g. 2026-04-24T17:30:39.123Z
  [[ "$iso" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$ ]] \
    || { fail "iso not matching ISO-8601 ms-Z format: $iso"; return; }
  ok "iso is ISO-8601 with millisecond precision"
}

# --- 6. Non-writable memory-dir → stderr + non-zero exit, no crash --------
# Skipped when running as root: chmod -w is ineffective for uid 0, producing
# a false pass.
test_unwritable_memdir() {
  if [[ "$(id -u)" -eq 0 ]]; then
    ok "unwritable-memdir: skipped (running as root)"
    return
  fi
  local mem="$TMP/readonly"
  mkdir -p "$mem"
  chmod -w "$mem"
  local rc err
  err="$(bash "$SCRIPT" start p s "$mem" 2>&1 >/dev/null)" && rc=0 || rc=$?
  chmod +w "$mem"
  [[ $rc -ne 0 ]] || { fail "expected non-zero exit for unwritable dir, got 0"; return; }
  grep -qi 'phase-timer.sh' <<<"$err" || { fail "stderr missing 'phase-timer.sh' prefix: $err"; return; }
  grep -qi 'write\|permission\|cannot' <<<"$err" \
    || { fail "stderr missing write-failure language: $err"; return; }
  ok "unwritable memdir: non-zero + stderr message"
}

# --- 7. Portability: PATH without GNU date uses python3 fallback ----------
test_python_fallback() {
  local mem="$TMP/mem3"
  mkdir -p "$mem"
  # Build a PATH that excludes GNU date (Homebrew's /opt/homebrew/opt/coreutils/libexec/gnubin
  # or /usr/local/opt/coreutils/libexec/gnubin). Keep BSD /bin/date + python3.
  local stripped_path
  stripped_path="$(echo "$PATH" | tr ':' '\n' | grep -v 'coreutils\|gnubin' | paste -sd':' -)"
  # Ensure python3 still resolves.
  PATH="$stripped_path" command -v python3 >/dev/null \
    || { fail "python3 not on stripped PATH; cannot validate fallback"; return; }
  PATH="$stripped_path" bash "$SCRIPT" start p s "$mem" >/dev/null \
    || { fail "start failed with stripped PATH"; return; }
  local ms
  ms="$(python3 -c 'import json,sys;print(json.loads(open(sys.argv[1]).readline())["epoch_ms"])' "$mem/phase-timings-s.jsonl")"
  # epoch_ms should be ~13 digits (ms since epoch). Today in ms is ~1.75e12.
  [[ "$ms" =~ ^[0-9]{13}$ ]] \
    || { fail "epoch_ms not 13-digit ms value: $ms"; return; }
  ok "python3 fallback produces ms-precision epoch"
}

echo "=== phase-timer tests ==="
test_help
test_missing_args
test_round_trip
test_default_memory_dir
test_iso_format
test_unwritable_memdir
test_python_fallback

if [[ $FAILED -gt 0 ]]; then
  echo "=== FAILED: $FAILED test(s) ==="
  exit 1
fi
echo "=== all phase-timer tests passed ==="
exit 0
