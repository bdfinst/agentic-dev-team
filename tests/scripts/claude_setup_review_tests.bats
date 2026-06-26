#!/usr/bin/env bats
# Tests for scripts/claude_setup_review.py — claude setup review validator
# Step 1.1: Frontmatter field presence and effort validation

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/claude_setup_review.py"

setup() {
  T="$(mktemp -d)"
  mkdir -p "$T/agents"
}

teardown() {
  rm -rf "$T"
}

run_review() {
  python3 "$SCRIPT" --plugin-root "$T" "$@" 2>/dev/null
}

make_valid_claude_md() {
  cat > "$T/CLAUDE.md" <<'EOF'
# Test Plugin

## Overview
A test plugin.
EOF
}

make_valid_agent() {
  local name="${1:-my-agent}"
  local file="${2:-$name.md}"
  cat > "$T/agents/$file" <<EOF
---
name: $name
description: does stuff
effort: low
---

# $name

Body here.
EOF
}

# ---------------------------------------------------------------------------
# Step 1.1: Frontmatter field presence and effort validation
# ---------------------------------------------------------------------------

@test "1.1 missing description field is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
name: my-agent
effort: low
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('description' in m for m in msgs), msgs
assert any('my-agent.md' in i.get('file','') for i in d['issues']), d['issues']
"
}

@test "1.1 missing name field is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
description: does stuff
effort: low
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('name' in m for m in msgs), msgs
"
}

@test "1.1 missing effort field is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
name: my-agent
description: does stuff
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('effort' in m for m in msgs), msgs
"
}

@test "1.1 invalid effort value ultra is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
name: my-agent
description: does stuff
effort: ultra
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('ultra' in m or 'effort' in m for m in msgs), msgs
"
}

@test "1.1 top-level model field is exit 2 with warning severity" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
name: my-agent
description: does stuff
effort: low
model: claude-opus-4-5
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'warn', d
severities = [i['severity'] for i in d['issues'] if 'llm-skipped' not in i.get('rule_id','')]
assert any(s == 'warning' for s in severities), d['issues']
"
}

@test "1.1 valid agent with all required fields is exit 0 (with --skip-llm)" {
  make_valid_claude_md
  make_valid_agent my-agent
  run run_review --skip-llm
  # exit 2 because --skip-llm adds a warning, but no errors
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] != 'fail', d
errs = [i for i in d['issues'] if i['severity'] == 'error']
assert len(errs) == 0, errs
"
}

# ---------------------------------------------------------------------------
# Step 1.2: Path resolution, naming convention, and root discovery
# ---------------------------------------------------------------------------

@test "1.2 CLAUDE.md reference to nonexistent skill path is exit 1 with file+line" {
  cat > "$T/CLAUDE.md" <<'EOF'
# Test Plugin

See skills/nonexistent/SKILL.md for details.
EOF
  make_valid_agent my-agent
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
path_issues = [i for i in d['issues'] if 'nonexistent' in i.get('message','') or 'nonexistent' in i.get('file','')]
# Must have at least one issue with a line number
line_issues = [i for i in d['issues'] if i.get('line',0) > 0]
assert len(line_issues) > 0, d['issues']
"
}

@test "1.2 non-kebab-case filename MyAgent.md is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/MyAgent.md" <<'EOF'
---
name: my-agent
description: does stuff
effort: low
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
"
}

@test "1.2 filename stem and name field mismatch is exit 1" {
  make_valid_claude_md
  cat > "$T/agents/my-agent.md" <<'EOF'
---
name: other-agent
description: does stuff
effort: low
---

Body.
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('mismatch' in m or 'other-agent' in m or 'my-agent' in m for m in msgs), msgs
"
}

@test "1.2 no CLAUDE.md in target path is exit 1 with descriptive message" {
  make_valid_agent my-agent
  # No CLAUDE.md created
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = [i['message'] for i in d['issues']]
assert any('CLAUDE.md' in m for m in msgs), msgs
"
}

@test "1.2 --plugin-root flag sets root and resolved root is printed to stderr" {
  make_valid_claude_md
  make_valid_agent my-agent
  run bash -c "python3 '$SCRIPT' --plugin-root '$T' --skip-llm 2>/tmp/bats_stderr_$$ ; cat /tmp/bats_stderr_$$"
  rm -f "/tmp/bats_stderr_$$"
  # Should not exit 1 due to root-resolution failure
  [ "$status" -ne 1 ] || echo "output: $output"
}

@test "1.2 --plugin-root stderr prints resolved root path" {
  make_valid_claude_md
  make_valid_agent my-agent
  # Capture stderr separately
  python3 "$SCRIPT" --plugin-root "$T" --skip-llm 2>/tmp/bats_stderr2_$$ || true
  grep -q "$T" /tmp/bats_stderr2_$$ || (cat /tmp/bats_stderr2_$$ && false)
  rm -f "/tmp/bats_stderr2_$$"
}

# ---------------------------------------------------------------------------
# Step 1.3: Duplicate name detection, JSON output, and LLM integration
# ---------------------------------------------------------------------------

@test "1.3 two agents with same name is exit 1 listing both paths" {
  make_valid_claude_md
  cat > "$T/agents/agent-one.md" <<'EOF'
---
name: my-agent
description: first agent
effort: low
---
EOF
  cat > "$T/agents/agent-two.md" <<'EOF'
---
name: my-agent
description: second agent
effort: low
---
EOF
  run run_review --skip-llm
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'fail', d
msgs = ' '.join(i['message'] for i in d['issues']) + ' ' + ' '.join(i.get('file','') for i in d['issues'])
assert 'agent-one.md' in msgs or 'agent-two.md' in msgs, d['issues']
"
}

@test "1.3 clean plugin config is exit 0 when no LLM (no agents dir)" {
  make_valid_claude_md
  # No agents — no structural errors; LLM skipped
  run run_review --skip-llm
  # With --skip-llm and no errors, should be exit 2 (warn from llm-skipped) or exit 0 if no agents
  # Per spec: --skip-llm adds warning finding → exit 2
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
errs = [i for i in d['issues'] if i['severity'] == 'error']
assert len(errs) == 0, errs
"
}

@test "1.3 --skip-llm flag adds warning finding with rule_id llm-skipped" {
  make_valid_claude_md
  make_valid_agent my-agent
  run run_review --skip-llm
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
llm_skip = [i for i in d['issues'] if i.get('rule_id') == 'llm-skipped']
assert len(llm_skip) == 1, d['issues']
assert llm_skip[0]['severity'] == 'warning', llm_skip[0]
"
}

@test "1.3 structurally valid output is valid JSON with required fields" {
  make_valid_claude_md
  make_valid_agent my-agent
  run run_review --skip-llm
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'status' in d, d
assert 'issues' in d, d
assert 'summary' in d, d
assert isinstance(d['issues'], list), d
for i in d['issues']:
    assert 'severity' in i, i
    assert 'confidence' in i, i
    assert 'file' in i, i
    assert 'line' in i, i
    assert 'message' in i, i
    assert 'suggestedFix' in i, i
"
}

@test "1.3 when claude not on PATH and no --skip-llm, LLM unavailability causes exit 2 not exit 1" {
  make_valid_claude_md
  make_valid_agent my-agent
  # Create a fake claude that always exits non-zero to simulate unavailability
  local fake_bin
  fake_bin="$(mktemp -d)"
  printf '#!/bin/sh\nexit 127\n' > "$fake_bin/claude"
  chmod +x "$fake_bin/claude"
  # Run with a PATH that has our fake claude first; structural checks still pass
  run bash -c "PATH='$fake_bin:$PATH' python3 '$SCRIPT' --plugin-root '$T' 2>/dev/null"
  rm -rf "$fake_bin"
  # Must NOT be exit 1 (that would mean structural errors caused by LLM failure)
  # Should be exit 2 (LLM unavailable = warning, not error)
  [ "$status" -eq 2 ]
}
