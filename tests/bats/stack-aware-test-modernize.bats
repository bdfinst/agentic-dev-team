#!/usr/bin/env bats
#
# Verifies plugins/dev-team/skills/test-modernize/SKILL.md is wired for
# stack-aware reference loading per plans/stack-aware-reference-loading.md
# (Slice 3, issue #524).
#
# Pattern source: plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62.

TARGET="plugins/dev-team/skills/test-modernize/SKILL.md"

# Mirrored in tests/bats/stack-aware-test-smell-review.bats and
# tests/bats/stack-aware-cd-test-architecture.bats — keep in sync.
BANNED_TOKENS='csharp|dotnet|HttpClient|HttpMessageHandler'

body_only() {
  awk '
    BEGIN { in_fm = 0; in_fence = 0; first = 1 }
    /^---$/ {
      if (first) { in_fm = 1; first = 0; next }
      if (in_fm) { in_fm = 0; next }
    }
    in_fm { next }
    /^```/ { in_fence = !in_fence; next }
    in_fence { next }
    { gsub(/`[^`]*`/, ""); print }
  '
}

@test "test-modernize names test-stack-profiles and cross-references test-design-advisor" {
  grep -q 'test-stack-profiles' "$TARGET"
  grep -q 'test-design-advisor' "$TARGET"
}

@test "test-modernize lists all six manifest tokens for stack detection" {
  grep -q 'package\.json' "$TARGET"
  grep -qE '\.csproj' "$TARGET"
  grep -qE 'pom\.xml|build\.gradle' "$TARGET"
  grep -q 'go\.mod' "$TARGET"
  grep -qE 'pyproject\.toml|requirements\.txt' "$TARGET"
  grep -q 'htmx' "$TARGET"
}

@test "test-modernize documents the missing-profile fallback phrase" {
  grep -q 'name the missing profile' "$TARGET"
}

@test "test-modernize argument-hint includes --stack" {
  # Extract the frontmatter (first --- block) and grep argument-hint line.
  fm=$(awk 'BEGIN{f=0} /^---$/{f++; next} f==1{print}' "$TARGET")
  echo "$fm" | grep -E 'argument-hint:' | grep -q -- '--stack'
}

@test "test-modernize Phase-1 invocation forwards --stack to /cd-test-architecture" {
  # Find the first 'Invoke' line that mentions /cd-test-architecture (allowing
  # backtick decoration), then check the 10 lines surrounding it for the
  # literal token '--stack'. This is the positional check from the plan
  # (Slice 3 assertion 3) — catches the case where --stack is documented
  # elsewhere but missing from the actual Phase-1 invocation.
  line=$(grep -nE 'Invoke `?/cd-test-architecture' "$TARGET" | head -1 | cut -d: -f1)
  [ -n "$line" ]
  start=$(( line > 5 ? line - 5 : 1 ))
  end=$(( line + 5 ))
  window=$(sed -n "${start},${end}p" "$TARGET")
  echo "$window" | grep -q -- '--stack'
}

@test "test-modernize body contains no language-specific tokens (frontmatter/fences excluded)" {
  count=$(body_only < "$TARGET" | grep -Ec "$BANNED_TOKENS" || true)
  [ "$count" -eq 0 ]
}
