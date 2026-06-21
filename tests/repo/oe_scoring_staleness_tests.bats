#!/usr/bin/env bats
# OE scoring staleness alert: detects when subject prose / fixtures / expected
# change (or are added) after a scoring snapshot, so the scorecard's currency is
# visible. Model-free (SHA-256 of inputs), so it runs in CI like the grader.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/scripts/oe_scoring_staleness.py"

setup() {
  TMP="$(mktemp -d)"
  SUITE="$TMP/suite"
  ROOT="$TMP/root"
  MAN="$TMP/manifest.json"
  mkdir -p "$SUITE/expected" "$SUITE/fixtures" "$ROOT/specs"

  cat > "$SUITE/subjects.json" <<'EOF'
{ "alpha": ["specs/alpha.md"], "beta": ["specs/beta.md"] }
EOF
  printf 'alpha v1\n' > "$ROOT/specs/alpha.md"
  printf 'beta v1\n'  > "$ROOT/specs/beta.md"

  cat > "$SUITE/expected/oe-01-thing.json" <<'EOF'
{"fixture":"oe-01-thing.md","subjects":["alpha","beta"]}
EOF
  printf 'scenario one\n' > "$SUITE/fixtures/oe-01-thing.md"
}
teardown() { rm -rf "$TMP"; }

_write() { python3 "$SCRIPT" --write --suite-dir "$SUITE" --repo-root "$ROOT" --manifest "$MAN"; }
_check() { python3 "$SCRIPT" --suite-dir "$SUITE" --repo-root "$ROOT" --manifest "$MAN"; }

@test "fresh snapshot reports OK and exits 0" {
  _write
  run _check
  [ "$status" -eq 0 ]
  [[ "$output" == *"OK — all scored"* ]]
}

@test "missing manifest is reported and exits non-zero" {
  run _check
  [ "$status" -ne 0 ]
  [[ "$output" == *"NO MANIFEST"* ]]
}

@test "a changed subject spec marks its pairs stale and exits non-zero" {
  _write
  printf 'alpha v2 (edited)\n' > "$ROOT/specs/alpha.md"
  run _check
  [ "$status" -eq 1 ]
  [[ "$output" == *"STALE"* ]]
  [[ "$output" == *"oe-01-thing::alpha"* ]]
  [[ "$output" == *"subject prose changed"* ]]
  # beta was untouched, so its pair must NOT be flagged stale
  [[ "$output" != *"oe-01-thing::beta"* ]]
}

@test "a changed expected file marks all that fixture's pairs stale" {
  _write
  printf '{"fixture":"oe-01-thing.md","subjects":["alpha","beta"],"x":1}\n' > "$SUITE/expected/oe-01-thing.json"
  run _check
  [ "$status" -eq 1 ]
  [[ "$output" == *"oe-01-thing::alpha"* ]]
  [[ "$output" == *"oe-01-thing::beta"* ]]
  [[ "$output" == *"expected criteria changed"* ]]
}

@test "a new (never-scored) fixture is reported as NEW" {
  _write
  cat > "$SUITE/expected/oe-02-new.json" <<'EOF'
{"fixture":"oe-02-new.md","subjects":["alpha"]}
EOF
  printf 'scenario two\n' > "$SUITE/fixtures/oe-02-new.md"
  run _check
  [ "$status" -eq 1 ]
  [[ "$output" == *"NEW"* ]]
  [[ "$output" == *"oe-02-new::alpha"* ]]
  [[ "$output" == *"never scored"* ]]
}

@test "--warn-only prints the alert but exits 0 (advisory CI mode)" {
  _write
  printf 'alpha v2\n' > "$ROOT/specs/alpha.md"
  run python3 "$SCRIPT" --suite-dir "$SUITE" --repo-root "$ROOT" --manifest "$MAN" --warn-only
  [ "$status" -eq 0 ]
  [[ "$output" == *"STALE"* ]]
}

@test "the real repo manifest parses and resolves against the live suite" {
  # Smoke-only: the staleness signal is deliberately ADVISORY (ci-local runs it
  # with --warn-only), so we do NOT hard-assert the manifest is current here —
  # that would turn a cosmetic subject edit into a test-suite failure. We only
  # assert the checker runs end-to-end against the real tree and emits a report.
  run python3 "$REPO_ROOT/scripts/oe_scoring_staleness.py" --warn-only
  [ "$status" -eq 0 ]
  [[ "$output" == *"OE scoring staleness"* ]]
}
