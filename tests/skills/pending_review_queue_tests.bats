#!/usr/bin/env bats
# Tests for the pending-review queue contract: format strings in skill files
# and session-model-banner.sh notification logic.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SESSION_REVIEW="$REPO_ROOT/plugins/dev-team/skills/session-review/SKILL.md"
FEEDBACK_LEARNING="$REPO_ROOT/plugins/dev-team/skills/feedback-learning/SKILL.md"
BANNER="$REPO_ROOT/plugins/dev-team/hooks/session-model-banner.sh"

# ---------------------------------------------------------------------------
# Schema contract: skills reference the queue and required fields
# ---------------------------------------------------------------------------

@test "session-review: references pending-review.jsonl" {
  grep -q "pending-review.jsonl" "$SESSION_REVIEW"
}

@test "session-review: references queued_at schema field" {
  grep -q "queued_at" "$SESSION_REVIEW"
}

@test "feedback-learning: references reviewed_at field" {
  grep -q "reviewed_at" "$FEEDBACK_LEARNING"
}

@test "feedback-learning: references approved_by field" {
  grep -q "approved_by" "$FEEDBACK_LEARNING"
}

@test "feedback-learning: references rejected_at field" {
  grep -q "rejected_at" "$FEEDBACK_LEARNING"
}

@test "feedback-learning: references rejected_by field" {
  grep -q "rejected_by" "$FEEDBACK_LEARNING"
}

@test "session-model-banner.sh: references pending-review.jsonl" {
  grep -q "pending-review.jsonl" "$BANNER"
}

# ---------------------------------------------------------------------------
# Banner notification: emits N queued finding(s) when unreviewed entries exist
# ---------------------------------------------------------------------------

setup() {
  BATS_TMPDIR_CASE="$(mktemp -d)"
  mkdir -p "$BATS_TMPDIR_CASE/knowledge"
  cat > "$BATS_TMPDIR_CASE/knowledge/model-routing.json" <<'EOF'
{
  "low": "claude-haiku-4-5-20251001",
  "medium": "claude-sonnet-4-6",
  "high": "claude-opus-4-8",
  "haiku": "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus": "claude-opus-4-8",
  "rounding": "round_half_up"
}
EOF
  export MODEL_ROUTING_JSON="$BATS_TMPDIR_CASE/knowledge/model-routing.json"
  export MODEL_LADDER_JSON="$BATS_TMPDIR_CASE/.claude/model-ladder.json"
  export SESSION_MODEL_FILE="$BATS_TMPDIR_CASE/.claude/session-model"
}

teardown() {
  rm -rf "$BATS_TMPDIR_CASE"
  unset MODEL_ROUTING_JSON MODEL_LADDER_JSON SESSION_MODEL_FILE
}

_session_input() {
  jq -nc --arg cwd "$BATS_TMPDIR_CASE" \
    '{hook_event_name:"SessionStart", cwd:$cwd, model:"claude-sonnet-4-6"}'
}

_run_banner_stdout() {
  bash -c "echo '$(_session_input)' | bash '$BANNER' 2>/dev/null"
}

@test "banner: silent when metrics/pending-review.jsonl does not exist" {
  run _run_banner_stdout
  ! echo "$output" | grep -q "queued finding"
}

@test "banner: silent when all entries have reviewed_at" {
  mkdir -p "$BATS_TMPDIR_CASE/metrics"
  printf '%s\n' \
    '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[],"reviewed_at":"2026-06-02T00:00:00Z"}' \
    > "$BATS_TMPDIR_CASE/metrics/pending-review.jsonl"
  run _run_banner_stdout
  ! echo "$output" | grep -q "queued finding"
}

@test "banner: emits count when entries lack reviewed_at" {
  mkdir -p "$BATS_TMPDIR_CASE/metrics"
  printf '%s\n' \
    '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}' \
    '{"queued_at":"2026-06-02T00:00:00Z","source":"auto","session_id":"s2","findings":[]}' \
    '{"queued_at":"2026-06-03T00:00:00Z","source":"auto","session_id":"s3","findings":[]}' \
    > "$BATS_TMPDIR_CASE/metrics/pending-review.jsonl"
  run _run_banner_stdout
  echo "$output" | grep -q "3 queued finding"
}

@test "banner: notification includes /session-review instruction" {
  mkdir -p "$BATS_TMPDIR_CASE/metrics"
  printf '%s\n' \
    '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}' \
    > "$BATS_TMPDIR_CASE/metrics/pending-review.jsonl"
  run _run_banner_stdout
  echo "$output" | grep -q "session-review"
}

@test "banner: only counts entries without reviewed_at" {
  mkdir -p "$BATS_TMPDIR_CASE/metrics"
  printf '%s\n' \
    '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}' \
    '{"queued_at":"2026-06-02T00:00:00Z","source":"auto","session_id":"s2","findings":[],"reviewed_at":"2026-06-02T12:00:00Z"}' \
    > "$BATS_TMPDIR_CASE/metrics/pending-review.jsonl"
  run _run_banner_stdout
  echo "$output" | grep -q "1 queued finding"
}
