#!/usr/bin/env bats
# Delta D extractor slice (#178): cross-project, incremental, per-session sync.
# Builds a fake ~/.claude/projects tree with two projects and verifies the
# --sync-out mode emits one metrics-only record per new/changed session, labels
# each by project basename, and is incremental via the watermark.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
EXTRACT="$REPO_ROOT/scripts/session_extract.py"
PLUGIN="$REPO_ROOT/plugins/dev-team"

setup() {
  ROOT="$(mktemp -d)"
  PROJECTS="$ROOT/projects"
  mkdir -p "$PROJECTS/projA" "$PROJECTS/projB"
  # One transcript per project. Filename stem = session id. cwd basename = project.
  printf '%s\n' \
    '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-a","isSidechain":false,"timestamp":"2026-06-07T10:00:00Z","message":{"model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":100,"cache_read_input_tokens":400}}}' \
    > "$PROJECTS/projA/sess-a.jsonl"
  printf '%s\n' \
    '{"type":"assistant","cwd":"/srv/code/beta","sessionId":"s-b","isSidechain":true,"timestamp":"2026-06-07T11:00:00Z","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":2000,"output_tokens":200}}}' \
    > "$PROJECTS/projB/sess-b.jsonl"
  OUT="$ROOT/digests/testhost/session-digest.jsonl"
  WM="$ROOT/watermark.json"
}
teardown() { rm -rf "$ROOT"; }

_sync() {
  python3 "$EXTRACT" --sync-out "$OUT" --watermark "$WM" \
    --projects-root "$PROJECTS" --host testhost --plugin-root "$PLUGIN"
}

@test "sync: emits one record per session across projects, labeled by basename" {
  run _sync
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$OUT")" -eq 2 ]
  # records carry identity + the sync schema
  run jq -r 'select(.session_id=="sess-a") | .schema' "$OUT"
  [ "$output" = "session-sync/v1" ]
  [ "$(jq -r 'select(.session_id=="sess-a").project' "$OUT")" = "alpha" ]
  [ "$(jq -r 'select(.session_id=="sess-b").project' "$OUT")" = "beta" ]
  [ "$(jq -r 'select(.session_id=="sess-a").host' "$OUT")" = "testhost" ]
  # ts comes from transcript data, not wall-clock
  [ "$(jq -r 'select(.session_id=="sess-a").ts' "$OUT")" = "2026-06-07T10:00:00Z" ]
  # main/subagent thread split is preserved
  [ "$(jq -r 'select(.session_id=="sess-b").by_thread.sidechain' "$OUT")" = "1" ]
}

@test "sync: incremental — a second run with no changes emits nothing new" {
  _sync
  before="$(wc -l < "$OUT")"
  _sync
  after="$(wc -l < "$OUT")"
  [ "$before" -eq 2 ]
  [ "$after" -eq 2 ]
  # watermark records both sessions
  [ "$(jq -r '.synced | keys | length' "$WM")" = "2" ]
}

@test "sync: a newly added session is the only new emission on re-run" {
  _sync
  printf '%s\n' \
    '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-c","timestamp":"2026-06-07T12:00:00Z","message":{"model":"claude-opus-4-8","usage":{"input_tokens":500,"output_tokens":50}}}' \
    > "$PROJECTS/projA/sess-c.jsonl"
  _sync
  [ "$(wc -l < "$OUT")" -eq 3 ]
  # exactly one record for the new session
  [ "$(jq -rs '[.[] | select(.session_id=="sess-c")] | length' "$OUT")" = "1" ]
}

@test "sync: a grown session is re-emitted (size watermark)" {
  _sync
  # append another usage record to an existing session -> file grows
  printf '%s\n' \
    '{"type":"assistant","cwd":"/home/u/work/alpha","sessionId":"s-a","timestamp":"2026-06-07T10:05:00Z","message":{"model":"claude-opus-4-8","usage":{"input_tokens":300,"output_tokens":30}}}' \
    >> "$PROJECTS/projA/sess-a.jsonl"
  _sync
  # sess-a re-emitted (now appears twice in the append-only host digest)
  [ "$(jq -rs '[.[] | select(.session_id=="sess-a")] | length' "$OUT")" = "2" ]
}

@test "sync: privacy — basename only, no full paths or prompt/command content" {
  _sync
  run cat "$OUT"
  [[ "$output" != *"/home/u/work/alpha"* ]]   # no full cwd path
  [[ "$output" != *"/srv/code/beta"* ]]
  [[ "$output" == *"\"project\": \"alpha\""* || "$output" == *'"project":"alpha"'* ]]
}

@test "all-projects: non-sync digest aggregates sessions across projects" {
  run python3 "$EXTRACT" --all-projects --projects-root "$PROJECTS" --plugin-root "$PLUGIN"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -r '.sessions')" = "2" ]
}
