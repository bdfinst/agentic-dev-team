#!/usr/bin/env bash
# run-all-harness.test.sh — verifies run-all.sh propagates child-test failures.
#
# Creates a synthetic always-failing *.test.sh in a temp directory, invokes
# run-all.sh against it, and asserts:
#   1. run-all.sh exits non-zero
#   2. stdout contains "FAIL: <fixture-name>"
#
# This test is itself a *.test.sh file, so run-all.sh discovers and runs it
# alongside every other test. It uses its own isolated temp directory for
# the synthetic fixture so it does not interfere with sibling tests.

set -uo pipefail

THIS_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_ALL="$THIS_DIR/run-all.sh"

if [[ ! -x "$RUN_ALL" && ! -f "$RUN_ALL" ]]; then
  echo "run-all.self-test.sh: run-all.sh not found at $RUN_ALL" >&2
  exit 1
fi

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

# Build a minimal mirror: a tests/scripts/ dir with run-all.sh and one
# always-failing test. Copy run-all.sh rather than point at its real
# location so we control what gets discovered.
FAKE_TESTS_DIR="$TMP_ROOT/tests/scripts"
mkdir -p "$FAKE_TESTS_DIR"
cp "$RUN_ALL" "$FAKE_TESTS_DIR/run-all.sh"
cat > "$FAKE_TESTS_DIR/always-fails.test.sh" <<'FIXTURE'
#!/usr/bin/env bash
echo "this test is supposed to fail" >&2
exit 1
FIXTURE
chmod +x "$FAKE_TESTS_DIR/always-fails.test.sh"

# Run the runner; capture stdout + exit.
OUT_FILE="$TMP_ROOT/stdout.txt"
if bash "$FAKE_TESTS_DIR/run-all.sh" >"$OUT_FILE" 2>/dev/null; then
  echo "run-all.self-test.sh: expected non-zero exit, got 0" >&2
  cat "$OUT_FILE" >&2
  exit 1
fi

if ! grep -q '^FAIL: always-fails$' "$OUT_FILE"; then
  echo "run-all.self-test.sh: expected 'FAIL: always-fails' in stdout, got:" >&2
  cat "$OUT_FILE" >&2
  exit 1
fi

echo "run-all.self-test.sh: ok"
exit 0
