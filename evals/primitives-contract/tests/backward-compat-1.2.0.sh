#!/usr/bin/env bash
# Asserts:
#   AC-10:   A pre-1.2.0 envelope validates against the 1.2.0 schema.
#   AC-10a:  The consumer-stub-fail-open.sh emits the documented one-time
#            notice on branch a (field absent).
#   AC-13 b: Same on branch b (sibling absent).
#   AC-13 c: Same on branch c (count mismatch).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCHEMA="$REPO_ROOT/plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json"
FIXTURE_DIR="$REPO_ROOT/evals/primitives-contract/fixtures"
VALIDATE="$REPO_ROOT/evals/primitives-contract/validate.sh"
STUB="$FIXTURE_DIR/consumer-stub-fail-open.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0

# AC-10: pre-1.2.0 envelope still validates.
if "$VALIDATE" "$SCHEMA" "$FIXTURE_DIR/recon-envelope-pre-1.2.0.json" >"$TMP/val.out" 2>&1; then
  printf '[ok]   AC-10: pre-1.2.0 envelope validates against 1.2.0 schema\n'
else
  printf '[FAIL] AC-10: pre-1.2.0 envelope did NOT validate\n' >&2
  cat "$TMP/val.out" >&2
  fail=$((fail + 1))
fi

# AC-10a (branch a — field absent).
STDERR_OUT="$TMP/stderr-a.txt"
set +e
"$STUB" "$FIXTURE_DIR/recon-envelope-pre-1.2.0.json" "$TMP" 2>"$STDERR_OUT"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  printf '[FAIL] AC-10a: stub exit %d (expected 0 — fail-open)\n' "$rc" >&2
  fail=$((fail + 1))
elif ! grep -q 'file_inventory field absent on envelope; proceeding without membership check' "$STDERR_OUT"; then
  printf '[FAIL] AC-10a: branch-a notice missing from stderr\n' >&2
  cat "$STDERR_OUT" >&2
  fail=$((fail + 1))
else
  printf '[ok]   AC-10a: branch-a (field absent) emits documented notice\n'
fi

# AC-13 branch b — sibling absent.
# Build a temp envelope that DOES declare file_inventory, but the referenced
# sibling file does not exist in <memory-dir>.
cat >"$TMP/envelope-b.json" <<'EOF'
{
  "schema_version": "1.0",
  "generated_at": "2026-04-24T12:00:00Z",
  "repo": {"name":"e","root":"/tmp/e","package_manager":"npm","monorepo":false,"workspaces":[],"vcs":{"kind":"git","remote_host":null,"default_branch":null}},
  "entry_points": [],
  "languages": [{"name":"TypeScript","file_count":1,"dominant_framework":null}],
  "dependencies": {},
  "architecture": {"summary":"x","layers":[{"name":"x","paths":["x"],"purpose":"x"}],"notable_anti_patterns":[]},
  "security_surface": {"auth_paths":[],"network_egress":[],"secrets_referenced":[],"crypto_calls":[],"csp_headers":[]},
  "git_history": {"branches":{"current":"main","main_count":1,"feature_count":0,"names":["main"]},"recent_activity":{"last_commit_date":"2026-04-23T12:00:00Z","commits_last_30d":0,"authors_last_30d":0},"sensitive_file_history":[]},
  "file_inventory": {"source":"git-ls-files","count":3,"sibling_ref":"recon-does-not-exist.inventory.txt"},
  "notes": []
}
EOF
STDERR_OUT="$TMP/stderr-b.txt"
set +e
"$STUB" "$TMP/envelope-b.json" "$TMP" 2>"$STDERR_OUT"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  printf '[FAIL] AC-13b: stub exit %d (expected 0 — fail-open)\n' "$rc" >&2
  fail=$((fail + 1))
elif ! grep -q 'sibling file .* missing; proceeding without membership check' "$STDERR_OUT"; then
  printf '[FAIL] AC-13b: branch-b notice missing from stderr\n' >&2
  cat "$STDERR_OUT" >&2
  fail=$((fail + 1))
else
  printf '[ok]   AC-13b: branch-b (sibling absent) emits documented notice\n'
fi

# AC-13 branch c — count mismatch.
cat >"$TMP/envelope-c.json" <<'EOF'
{
  "schema_version": "1.0",
  "generated_at": "2026-04-24T12:00:00Z",
  "repo": {"name":"e","root":"/tmp/e","package_manager":"npm","monorepo":false,"workspaces":[],"vcs":{"kind":"git","remote_host":null,"default_branch":null}},
  "entry_points": [],
  "languages": [{"name":"TypeScript","file_count":1,"dominant_framework":null}],
  "dependencies": {},
  "architecture": {"summary":"x","layers":[{"name":"x","paths":["x"],"purpose":"x"}],"notable_anti_patterns":[]},
  "security_surface": {"auth_paths":[],"network_egress":[],"secrets_referenced":[],"crypto_calls":[],"csp_headers":[]},
  "git_history": {"branches":{"current":"main","main_count":1,"feature_count":0,"names":["main"]},"recent_activity":{"last_commit_date":"2026-04-23T12:00:00Z","commits_last_30d":0,"authors_last_30d":0},"sensitive_file_history":[]},
  "file_inventory": {"source":"git-ls-files","count":99,"sibling_ref":"recon-mismatch.inventory.txt"},
  "notes": []
}
EOF
printf 'one.ts\ntwo.ts\n' >"$TMP/recon-mismatch.inventory.txt"
STDERR_OUT="$TMP/stderr-c.txt"
set +e
"$STUB" "$TMP/envelope-c.json" "$TMP" 2>"$STDERR_OUT"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  printf '[FAIL] AC-13c: stub exit %d (expected 0 — fail-open)\n' "$rc" >&2
  fail=$((fail + 1))
elif ! grep -q 'file_inventory.count (99) != wc -l .* (2); proceeding without membership check' "$STDERR_OUT"; then
  printf '[FAIL] AC-13c: branch-c notice missing or malformed\n' >&2
  cat "$STDERR_OUT" >&2
  fail=$((fail + 1))
else
  printf '[ok]   AC-13c: branch-c (count mismatch) emits documented notice\n'
fi

if [[ $fail -ne 0 ]]; then
  printf '\nFAIL: %d check(s) failed\n' "$fail" >&2
  exit 1
fi
printf '\nOK: backward-compat + fail-open tests passed\n'
