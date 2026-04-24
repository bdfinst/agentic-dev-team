#!/usr/bin/env bash
# Tests the canonical recon-inventory.sh against the polyglot fixture with a
# scratch git repo. Mirrors inventory-ts-monorepo.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/plugins/agentic-dev-team/scripts/recon-inventory.sh"
FIXTURE_SRC="$REPO_ROOT/evals/codebase-recon/fixtures/polyglot"
EXPECTED_INVENTORY="$FIXTURE_SRC/expected-inventory.txt"
EXPECTED_MAIN="$FIXTURE_SRC/expected-file-inventory.json"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SCRATCH="$TMP/polyglot"
mkdir -p "$SCRATCH"
(
  cd "$FIXTURE_SRC"
  tar --exclude='expected-inventory.txt' \
      --exclude='expected-file-inventory.json' \
      -cf - . | (cd "$SCRATCH" && tar -xf -)
)

(
  cd "$SCRATCH"
  git init -q
  git -c user.email=test@example.com -c user.name=Test add .
  git -c user.email=test@example.com -c user.name=Test commit -q -m "fixture seed"
) >/dev/null

MAIN_JSON_OUT="$TMP/main-fragment.json"
STDOUT_OUT="$TMP/stdout.txt"

set +e
"$SCRIPT" "$SCRATCH" --slug polyglot --emit-main-inventory-json "$MAIN_JSON_OUT" >"$STDOUT_OUT" 2>"$TMP/stderr.txt"
rc=$?
set -e

fail=0

if ! diff -u "$EXPECTED_INVENTORY" "$STDOUT_OUT"; then
  printf '[FAIL] stdout inventory mismatch vs %s\n' "$EXPECTED_INVENTORY" >&2
  fail=$((fail + 1))
else
  printf '[ok]   stdout inventory matches\n'
fi

if [[ ! -s "$MAIN_JSON_OUT" ]]; then
  printf '[FAIL] --emit-main-inventory-json produced no output\n' >&2
  fail=$((fail + 1))
elif ! diff -u "$EXPECTED_MAIN" "$MAIN_JSON_OUT"; then
  printf '[FAIL] main-envelope JSON fragment mismatch vs %s\n' "$EXPECTED_MAIN" >&2
  fail=$((fail + 1))
else
  printf '[ok]   main-envelope JSON fragment matches\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed (script exit %d)\n' "$fail" "$rc" >&2
  exit 1
fi
printf '\nOK: inventory-polyglot tests passed\n'
