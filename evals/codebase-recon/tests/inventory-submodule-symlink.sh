#!/usr/bin/env bash
# Exercises the submodule + symlink edge cases.
#
#   - Regular files src/handlers/auth.ts, src/index.ts appear once each.
#   - Symlink src/alias.ts resolves to src/handlers/auth.ts (already present);
#     the duplicate is deduped out.
#   - Broken symlink src/orphan.ts is dropped and recorded as a
#     `# BROKEN_SYMLINK:` note on stderr.
#   - Submodule gitlink at vendor/sub appears exactly once; no recursion into
#     the submodule's contents.
#
# The setup.sh companion creates the submodule at test time from a tiny bare
# stub (plan R2), keeping the committed fixture tree nested-.git-free.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/plugins/agentic-dev-team/scripts/recon-inventory.sh"
FIXTURE_SRC="$REPO_ROOT/evals/codebase-recon/fixtures/submodule-symlink"
EXPECTED_INVENTORY="$FIXTURE_SRC/expected-inventory.txt"
EXPECTED_MAIN="$FIXTURE_SRC/expected-file-inventory.json"
EXPECTED_NOTES="$FIXTURE_SRC/expected-notes.txt"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SCRATCH="$TMP/submodule-symlink"
mkdir -p "$SCRATCH"
(
  cd "$FIXTURE_SRC"
  tar --exclude='expected-inventory.txt' \
      --exclude='expected-file-inventory.json' \
      --exclude='expected-notes.txt' \
      --exclude='setup.sh' \
      -cf - . | (cd "$SCRATCH" && tar -xf -)
)

# Use setup.sh to build the submodule + symlinks at test time.
"$FIXTURE_SRC/setup.sh" "$SCRATCH"

MAIN_JSON_OUT="$TMP/main-fragment.json"
STDOUT_OUT="$TMP/stdout.txt"
STDERR_OUT="$TMP/stderr.txt"

set +e
"$SCRIPT" "$SCRATCH" --slug submodule-symlink \
  --emit-main-inventory-json "$MAIN_JSON_OUT" >"$STDOUT_OUT" 2>"$STDERR_OUT"
rc=$?
set -e

fail=0

if ! diff -u "$EXPECTED_INVENTORY" "$STDOUT_OUT"; then
  printf '[FAIL] stdout inventory mismatch\n' >&2
  printf '(stderr below for debug)\n' >&2
  cat "$STDERR_OUT" >&2
  fail=$((fail + 1))
else
  printf '[ok]   stdout inventory matches\n'
fi

if [[ ! -s "$MAIN_JSON_OUT" ]]; then
  printf '[FAIL] --emit-main-inventory-json produced no output\n' >&2
  fail=$((fail + 1))
elif ! diff -u "$EXPECTED_MAIN" "$MAIN_JSON_OUT"; then
  printf '[FAIL] main-envelope JSON fragment mismatch\n' >&2
  fail=$((fail + 1))
else
  printf '[ok]   main-envelope JSON fragment matches\n'
fi

# Extract only BROKEN_SYMLINK lines from stderr and compare to the oracle.
grep '^# BROKEN_SYMLINK:' "$STDERR_OUT" >"$TMP/actual-notes.txt" || true
if ! diff -u "$EXPECTED_NOTES" "$TMP/actual-notes.txt"; then
  printf '[FAIL] broken-symlink notes mismatch vs %s\n' "$EXPECTED_NOTES" >&2
  fail=$((fail + 1))
else
  printf '[ok]   broken-symlink notes match\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed (script exit %d)\n' "$fail" "$rc" >&2
  exit 1
fi
printf '\nOK: inventory-submodule-symlink tests passed\n'
