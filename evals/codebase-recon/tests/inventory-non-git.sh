#!/usr/bin/env bash
# Exercises the filesystem-walk branch of recon-inventory.sh against the
# non-git-basic fixture. Uses --force-filesystem-walk so the branch is
# exercised even though the enclosing dev-team repo IS a git repo.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/plugins/agentic-dev-team/scripts/recon-inventory.sh"
FIXTURE_SRC="$REPO_ROOT/evals/codebase-recon/fixtures/non-git-basic"
EXPECTED_INVENTORY="$FIXTURE_SRC/expected-inventory.txt"
EXPECTED_MAIN="$FIXTURE_SRC/expected-file-inventory.json"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Copy fixture tree out so the script does not see the oracle files.
SCRATCH="$TMP/non-git-basic"
mkdir -p "$SCRATCH"
(
  cd "$FIXTURE_SRC"
  tar --exclude='expected-inventory.txt' \
      --exclude='expected-file-inventory.json' \
      --exclude='setup.sh' \
      -cf - . | (cd "$SCRATCH" && tar -xf -)
)

# Materialise the two gitignored exclude-cases (.DS_Store + node_modules/).
"$FIXTURE_SRC/setup.sh" "$SCRATCH"

MAIN_JSON_OUT="$TMP/main-fragment.json"
STDOUT_OUT="$TMP/stdout.txt"

set +e
"$SCRIPT" "$SCRATCH" --slug non-git-basic --force-filesystem-walk \
  --emit-main-inventory-json "$MAIN_JSON_OUT" >"$STDOUT_OUT" 2>"$TMP/stderr.txt"
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
printf '\nOK: inventory-non-git tests passed\n'
