#!/usr/bin/env bats
# AC24: builder enforces jq >= 1.6 with a clear error on older versions.
# The version floor pins output formatting so the freshness gate doesn't
# flap across heterogeneous CI environments.

BUILDER="$BATS_TEST_DIRNAME/../../plugins/agentic-dev-team/hooks/lib/build-knowledge-index.sh"

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/fake-bin"
  mkdir -p "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge"
  cat > "$BATS_TMPDIR_CASE/plugins/agentic-dev-team/knowledge/foo.md" <<'EOF'
# F
## Bar
Body.
EOF
  export KNOWLEDGE_INDEX_CORPUS_ROOTS="$BATS_TMPDIR_CASE/plugins/agentic-dev-team"
  export KNOWLEDGE_INDEX_OUTPUT="$BATS_TMPDIR_CASE/index.json"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset KNOWLEDGE_INDEX_CORPUS_ROOTS KNOWLEDGE_INDEX_OUTPUT
}

@test "AC24: builder header documents jq >= 1.6 requirement" {
  run grep -E "jq[[:space:]]*>=?[[:space:]]*1\\.6|jq 1\\.6" "$BUILDER"
  [ "$status" -eq 0 ]
}

@test "AC24: builder exits non-zero when jq reports a version below 1.6" {
  # Install a fake jq shim that reports jq-1.5 (real jq is used for
  # everything else via the builder's normal PATH lookup — but we
  # prepend the shim so the version check sees 1.5).
  cat > "$BATS_TMPDIR_CASE/fake-bin/jq" <<'JQSHIM'
#!/usr/bin/env bash
if [[ "$1" == "--version" ]]; then
  echo "jq-1.5"
  exit 0
fi
# Real jq for any other invocation (which we should not reach).
exec /usr/bin/env -i PATH="/opt/homebrew/bin:/usr/bin:/bin" jq "$@"
JQSHIM
  chmod +x "$BATS_TMPDIR_CASE/fake-bin/jq"
  local stderr_file
  stderr_file=$(mktemp)
  run bash -c "PATH='$BATS_TMPDIR_CASE/fake-bin:$PATH' bash '$BUILDER' > /dev/null 2> '$stderr_file'"
  [ "$status" -ne 0 ]
  grep -qE "jq version" "$stderr_file"
  rm -f "$stderr_file"
}

@test "AC24: builder proceeds normally when jq reports 1.6+" {
  cat > "$BATS_TMPDIR_CASE/fake-bin/jq" <<JQSHIM
#!/usr/bin/env bash
if [[ "\$1" == "--version" ]]; then
  echo "jq-1.7.1"
  exit 0
fi
exec $(which jq) "\$@"
JQSHIM
  chmod +x "$BATS_TMPDIR_CASE/fake-bin/jq"
  run bash -c "PATH='$BATS_TMPDIR_CASE/fake-bin:$PATH' bash '$BUILDER'"
  [ "$status" -eq 0 ]
}
