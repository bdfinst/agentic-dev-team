#!/usr/bin/env bats

CLAUDE="$BATS_TEST_DIRNAME/../../plugins/dev-team/CLAUDE.md"

@test "CLAUDE.md is under 5000 characters" {
  python3 -c "
import sys
text = open('$CLAUDE').read()
assert len(text) < 5001, f'CLAUDE.md is {len(text)} chars, must be under 5001'
"
}

@test "CLAUDE.md references knowledge/skills-registry.md" {
  grep -q "knowledge/skills-registry.md" "$CLAUDE"
}

@test "CLAUDE.md references knowledge/request-processing-flow.md" {
  grep -q "knowledge/request-processing-flow.md" "$CLAUDE"
}

@test "CLAUDE.md does not contain the full skills registry table" {
  # The full table has 45+ rows; if the pointer replaced it, only 2 rows max
  count=$(grep -c "| \`/" "$CLAUDE" 2>/dev/null; true)
  count=${count:-0}
  [ "$count" -le 2 ]
}
