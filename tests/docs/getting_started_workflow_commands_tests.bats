#!/usr/bin/env bats
# #252 — GETTING-STARTED.md must list /specs as a workflow command and position
# the primary lifecycle commands ahead of the "Invoke a skill directly" section.
# Documentation gate.

DOC="$BATS_TEST_DIRNAME/../../GETTING-STARTED.md"

@test "workflow commands block lists /specs as the lifecycle entry point" {
  # The /specs line must live inside the workflow-commands fenced block, not only
  # in the skill-invocation examples.
  run awk '
    /^### Use the workflow commands/ { in_section=1 }
    in_section && /^### Invoke a skill directly/ { in_section=0 }
    in_section && /^\/specs/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$DOC"
  [ "$status" -eq 0 ]
}

@test "workflow commands section appears before 'Invoke a skill directly'" {
  workflow_line=$(grep -n '^### Use the workflow commands' "$DOC" | head -1 | cut -d: -f1)
  invoke_line=$(grep -n '^### Invoke a skill directly' "$DOC" | head -1 | cut -d: -f1)
  [ -n "$workflow_line" ]
  [ -n "$invoke_line" ]
  [ "$workflow_line" -lt "$invoke_line" ]
}

@test "primary lifecycle commands remain documented" {
  for cmd in '/specs' '/plan' '/build' '/pr' '/code-review' '/triage'; do
    grep -q -- "$cmd" "$DOC"
  done
}
