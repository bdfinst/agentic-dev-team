#!/usr/bin/env bats
# Tests for scripts/citation_lint.py — the preventive skill-citation drift lint
# (issue #312). Phase 1 is advisory (always exit 0); these pin the warning
# behaviour on a tiny self-contained plugin tree.

LINT="$BATS_TEST_DIRNAME/../../scripts/citation_lint.py"

setup() {
  T="$(mktemp -d)"
  mkdir -p "$T/agents" "$T/skills/complexity" "$T/knowledge"
  # A canonical skill that states the 50-line threshold.
  cat > "$T/skills/complexity/SKILL.md" <<'EOF'
# Complexity
Functions should be under 50 lines and 80% branch coverage is expected.
EOF
  echo "Object calisthenics: no more than 2 instance variables." \
    > "$T/knowledge/object-calisthenics.md"
}
teardown() { rm -rf "$T"; }

lint() { python3 "$LINT" --plugin-root "$T" "$@"; }

@test "cites present and every threshold backed -> no warning, exit 0" {
  cat > "$T/agents/clean.md" <<'EOF'
---
name: clean
cites: [complexity, object-calisthenics]
---
# Clean
Functions MUST be under 50 lines. Coverage SHOULD reach 80%.
Classes MUST hold no more than 2 instance variables.
EOF
  run lint "$T/agents/clean.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]
}

@test "cites present but a threshold is uncited -> warning with token + line" {
  cat > "$T/agents/drift.md" <<'EOF'
---
name: drift
cites: [complexity]
---
# Drift
Functions MUST be under 40 lines.
EOF
  run lint "$T/agents/drift.md"
  [ "$status" -eq 0 ]                        # Phase 1 non-blocking
  [[ "$output" == *"'40'"* ]]                # the drifted token
  [[ "$output" == *"drift:6:"* ]]            # token line number in the file
  [[ "$output" == *"possible drift"* ]]
}

@test "no cites and no normative tokens -> no warning" {
  cat > "$T/agents/prose.md" <<'EOF'
---
name: prose
---
# Prose
This agent reviews naming clarity and reports issues.
EOF
  run lint "$T/agents/prose.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]
}

@test "no cites but normative tokens -> advisory warning, exit 0" {
  cat > "$T/agents/advise.md" <<'EOF'
---
name: advise
---
# Advise
Functions MUST be under 50 lines.
EOF
  run lint "$T/agents/advise.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"advisory"* ]]
  [[ "$output" == *"declares no \`cites:\`"* ]]
}

@test "thresholds inside code fences are not flagged" {
  cat > "$T/agents/fenced.md" <<'EOF'
---
name: fenced
cites: [complexity]
---
# Fenced

```
Functions MUST be under 40 lines.
```
EOF
  run lint "$T/agents/fenced.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]    # the 40 in the fence is ignored
}

@test "thresholds inside blockquotes are not flagged" {
  cat > "$T/agents/quoted.md" <<'EOF'
---
name: quoted
cites: [complexity]
---
# Quoted
> Functions MUST be under 40 lines.
EOF
  run lint "$T/agents/quoted.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]
}

@test "cites an unknown source -> unverifiable-citation warning" {
  cat > "$T/agents/badcite.md" <<'EOF'
---
name: badcite
cites: [does-not-exist]
---
# BadCite
Functions MUST be under 50 lines.
EOF
  run lint "$T/agents/badcite.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"unknown source"* ]]
  [[ "$output" == *"does-not-exist"* ]]
}

@test "block-list cites: syntax is parsed" {
  cat > "$T/agents/block.md" <<'EOF'
---
name: block
cites:
  - complexity
  - object-calisthenics
---
# Block
Functions MUST be under 50 lines and hold no more than 2 variables.
EOF
  run lint "$T/agents/block.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]
}

@test "issue refs like #99 are not treated as thresholds" {
  cat > "$T/agents/issueref.md" <<'EOF'
---
name: issueref
cites: [complexity]
---
# IssueRef
This rule MUST follow the contract from #99 and #312.
EOF
  run lint "$T/agents/issueref.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Citation lint OK"* ]]    # 99 / 312 are issue refs, not thresholds
}
