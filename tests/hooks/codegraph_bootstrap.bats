#!/usr/bin/env bats
# Tests for hooks/codegraph-bootstrap.sh — the SessionStart hook that rebuilds
# the machine-local CodeGraph index on a fresh clone of a repo that adopted
# CodeGraph. See docs/adr/0012-auto-bootstrap-codegraph-index-per-clone.md.
#
# The hook's real build path is detached (background); tests drive the
# foreground path via CODEGRAPH_BOOTSTRAP_SYNC=1 and inject a fake `codegraph`
# binary via CODEGRAPH_BIN so no real indexing runs.

HOOK="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/codegraph-bootstrap.sh"

# Keep in sync with the message constants in codegraph-bootstrap.sh.
BUILD_MSG='[codegraph-bootstrap] This project uses CodeGraph but has no local index yet'
INSTALL_MSG='[codegraph-bootstrap] This project uses CodeGraph but it is not installed on this machine'

setup() {
  CASE="$(mktemp -d)"
  # A fake codegraph that "indexes" by creating the db the real one would.
  FAKE_BIN_DIR="$CASE/bin"
  mkdir -p "$FAKE_BIN_DIR"
  cat > "$FAKE_BIN_DIR/codegraph" <<'EOF'
#!/usr/bin/env bash
# init -> create the local index the real codegraph would build.
[ "${1:-}" = "init" ] && touch "$PWD/.codegraph/codegraph.db"
exit 0
EOF
  chmod +x "$FAKE_BIN_DIR/codegraph"
}

teardown() {
  rm -rf "$CASE"
}

_input() {
  jq -nc --arg cwd "$1" '{hook_event_name:"SessionStart", cwd:$cwd}'
}

@test "no .codegraph directory -> silent no-op, exit 0" {
  run bash -c "echo '$(_input "$CASE")' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "local index already present -> silent no-op, exit 0" {
  mkdir -p "$CASE/.codegraph"
  touch "$CASE/.codegraph/codegraph.db"
  run bash -c "echo '$(_input "$CASE")' | CODEGRAPH_BIN='$FAKE_BIN_DIR/codegraph' bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "adopted repo, no index, binary present -> builds the index" {
  mkdir -p "$CASE/.codegraph"
  run bash -c "echo '$(_input "$CASE")' | CODEGRAPH_BIN='$FAKE_BIN_DIR/codegraph' CODEGRAPH_BOOTSTRAP_SYNC=1 bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -f "$CASE/.codegraph/codegraph.db" ]
  [[ "$output" == *"$BUILD_MSG"* ]]
}

@test "adopted repo, no index, binary missing -> install nudge, no build" {
  mkdir -p "$CASE/.codegraph"
  run bash -c "echo '$(_input "$CASE")' | CODEGRAPH_BIN='/nonexistent/codegraph' bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ ! -f "$CASE/.codegraph/codegraph.db" ]
  [[ "$output" == *"$INSTALL_MSG"* ]]
}

@test "honors CODEGRAPH_DB_FILE override for the index-present check" {
  mkdir -p "$CASE/.codegraph"
  local alt="$CASE/.codegraph/custom.db"
  touch "$alt"
  run bash -c "echo '$(_input "$CASE")' | CODEGRAPH_DB_FILE='$alt' CODEGRAPH_BIN='$FAKE_BIN_DIR/codegraph' bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "malformed stdin fails open (silent, exit 0)" {
  run bash -c "echo 'not json' | bash '$HOOK'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "missing cwd in payload falls back to PWD without error" {
  # No .codegraph in the fallback dir -> safe no-op.
  run bash -c "cd '$CASE' && echo '{\"hook_event_name\":\"SessionStart\"}' | bash '$HOOK'"
  [ "$status" -eq 0 ]
}
