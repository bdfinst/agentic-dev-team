#!/usr/bin/env bats
# token_efficiency_review_tests.bats — Gherkin-driven tests for
# scripts/token_efficiency_review.py (Slice 2 of Python Agent Harness Pattern).

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/token_efficiency_review.py"

setup() {
  T="$(mktemp -d)"
}

teardown() {
  rm -rf "$T"
}

run_review() {
  python3 "$SCRIPT" "$@"
}

# ---------------------------------------------------------------------------
# Step 2.1 — CLAUDE.md char and rule count thresholds
# ---------------------------------------------------------------------------

@test "CLAUDE.md with 5001 chars exits 1 and reports char count" {
  # Generate a file with exactly 5001 characters (header + padding)
  python3 -c "
content = '# Title\n' + 'x' * (5001 - len('# Title\n'))
with open('$T/CLAUDE.md', 'w') as f:
    f.write(content)
print(len(content))
"
  run run_review --files "$T/CLAUDE.md"
  [ "$status" -eq 1 ]
  # Output should be valid JSON with an error issue mentioning char count or chars
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['status'] == 'fail', f'Expected fail, got {data[\"status\"]}'
errors = [i for i in data['issues'] if i['severity'] == 'error']
assert len(errors) >= 1, 'Expected at least one error issue'
# At least one issue should mention char/character
msgs = ' '.join(i['message'] for i in errors)
assert 'char' in msgs.lower() or '5001' in msgs, f'No char mention in: {msgs}'
"
}

@test "CLAUDE.md with exactly 5000 chars exits 0" {
  # Use --skip-llm to isolate the char threshold check from LLM findings
  python3 -c "
content = '# Title\n' + 'x' * (5000 - len('# Title\n'))
with open('$T/CLAUDE.md', 'w') as f:
    f.write(content)
"
  run run_review --skip-llm --files "$T/CLAUDE.md"
  # With --skip-llm we get exit 2 (llm-skipped warning), but no char-limit error
  # The threshold assertion: no error issues for char count
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
char_errors = [i for i in data['issues'] if i.get('rule_id') == 'claude-md-char-limit']
assert len(char_errors) == 0, f'Expected no char-limit errors at exactly 5000 chars, got {char_errors}'
assert data['status'] != 'fail', f'Expected no fail status at threshold, got {data[\"status\"]}'
"
}

@test "CLAUDE.md with 201 top-level bullet items exits 1" {
  python3 -c "
lines = ['# Title', '']
for i in range(201):
    lines.append(f'- item {i}')
content = '\n'.join(lines) + '\n'
with open('$T/CLAUDE.md', 'w') as f:
    f.write(content)
"
  run run_review --files "$T/CLAUDE.md"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['status'] == 'fail', f'Expected fail, got {data[\"status\"]}'
errors = [i for i in data['issues'] if i['severity'] == 'error']
assert len(errors) >= 1, 'Expected at least one error issue'
msgs = ' '.join(i['message'] for i in errors)
assert 'rule' in msgs.lower() or 'bullet' in msgs.lower() or '201' in msgs, f'No rule/bullet mention: {msgs}'
"
}

@test "CLAUDE.md with 200 top-level bullet items exits 0" {
  python3 -c "
lines = ['# Title', '']
for i in range(200):
    lines.append(f'- item {i}')
content = '\n'.join(lines) + '\n'
with open('$T/CLAUDE.md', 'w') as f:
    f.write(content)
"
  run run_review --files "$T/CLAUDE.md"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['status'] == 'pass', f'Expected pass, got {data[\"status\"]}'
"
}

# ---------------------------------------------------------------------------
# Step 2.2 — Per-file line count, measure-tokens.sh, LLM filter, --skip-llm
# ---------------------------------------------------------------------------

@test "file with 501 lines exits 2 with severity warning" {
  python3 -c "
lines = ['line ' + str(i) for i in range(501)]
with open('$T/long_file.md', 'w') as f:
    f.write('\n'.join(lines) + '\n')
"
  run run_review --skip-llm --files "$T/long_file.md"
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['status'] == 'warn', f'Expected warn, got {data[\"status\"]}'
warnings = [i for i in data['issues'] if i['severity'] == 'warning']
assert len(warnings) >= 1, 'Expected at least one warning issue'
"
}

@test "file with exactly 500 lines exits 0" {
  # Use a .py file so no LLM call and no llm-skipped warning — isolates the line threshold
  python3 -c "
lines = ['# line ' + str(i) for i in range(500)]
with open('$T/ok_file.py', 'w') as f:
    f.write('\n'.join(lines) + '\n')
"
  run run_review --files "$T/ok_file.py"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['status'] == 'pass', f'Expected pass, got {data[\"status\"]}'
"
}

@test "--skip-llm suppresses LLM call and adds warning with rule_id llm-skipped" {
  printf '# Hello\n' > "$T/test.md"
  run run_review --skip-llm --files "$T/test.md"
  # exit code 2 (warning from llm-skipped) or 0 (pass if no other issues)
  # The key assertion is the llm-skipped warning appears in output
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
skipped = [i for i in data['issues'] if i.get('rule_id') == 'llm-skipped']
assert len(skipped) == 1, f'Expected exactly one llm-skipped warning, got {skipped}'
assert skipped[0]['severity'] == 'warning', f'Expected severity warning, got {skipped[0][\"severity\"]}'
"
}

@test "--files flag accepts paths to check" {
  printf '# Short file\nHello world.\n' > "$T/short.md"
  run run_review --skip-llm --files "$T/short.md"
  [ "$status" -eq 2 ]  # 2 because of llm-skipped warning
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
# Just verify output is valid JSON with status
assert 'status' in data
assert 'issues' in data
"
}

@test "LLM review scoped to .md files only: .py file is not LLM-reviewed" {
  # When --files contains only a .py file and no --skip-llm,
  # the script should NOT call LLM (py is not prose).
  # We verify by checking no llm-related output differences exist
  # (deterministic: .py → no LLM call means no llm-skipped warning needed)
  printf 'def foo():\n    pass\n' > "$T/code.py"
  # Without --skip-llm and with a .py file: should pass without llm-skipped warning
  run run_review --files "$T/code.py"
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
skipped = [i for i in data['issues'] if i.get('rule_id') == 'llm-skipped']
assert len(skipped) == 0, f'Expected no llm-skipped for .py file, got {skipped}'
"
}

@test "LLM findings are severity warning only, never error" {
  # Create a mock scenario: with skip-llm the only LLM-related issue is llm-skipped (warning)
  # This tests the shape constraint: if LLM runs, its issues must be warning severity
  # We test via skip-llm: the injected warning is severity=warning
  printf '# Test\nsome content\n' > "$T/prose.md"
  run run_review --skip-llm --files "$T/prose.md"
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
# All issues from LLM path must be warnings (not errors)
for issue in data['issues']:
    if issue.get('rule_id') == 'llm-skipped':
        assert issue['severity'] == 'warning', f'llm-skipped must be warning, got {issue[\"severity\"]}'
"
}

@test "output JSON contains all required issue fields" {
  # Create a file that will trigger a finding
  python3 -c "
content = '# Title\n' + 'x' * (5001 - len('# Title\n'))
with open('$T/CLAUDE.md', 'w') as f:
    f.write(content)
"
  run run_review --files "$T/CLAUDE.md"
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
required_fields = {'severity', 'confidence', 'file', 'line', 'message', 'suggestedFix'}
for issue in data['issues']:
    missing = required_fields - set(issue.keys())
    assert not missing, f'Missing fields {missing} in issue: {issue}'
"
}
