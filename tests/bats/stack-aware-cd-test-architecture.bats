#!/usr/bin/env bats
#
# Verifies plugins/dev-team/skills/cd-test-architecture/SKILL.md is wired for
# stack-aware reference loading per plans/stack-aware-reference-loading.md
# (Slice 2, issue #524).
#
# Pattern source: plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62.

TARGET="plugins/dev-team/skills/cd-test-architecture/SKILL.md"

# Mirrored in tests/bats/stack-aware-test-smell-review.bats and
# tests/bats/stack-aware-test-modernize.bats — keep in sync. Bare 'C#' and
# '.NET' deliberately omitted (they appear in legitimate language-list contexts).
BANNED_TOKENS='csharp|dotnet|HttpClient|HttpMessageHandler'

body_only() {
  # Strip YAML frontmatter, fenced code blocks, and inline backtick spans.
  # Profile slugs and manifest filenames cited via `inline code` are legitimate
  # references (not language-specific guidance) — the rule we want to enforce
  # is "no language-specific tokens in flowing prose."
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

@test "cd-test-architecture names test-stack-profiles and cross-references test-design-advisor" {
  grep -q 'test-stack-profiles' "$TARGET"
  grep -q 'test-design-advisor' "$TARGET"
}

@test "cd-test-architecture lists all six manifest tokens for stack detection" {
  grep -q 'package\.json' "$TARGET"
  grep -qE '\.csproj' "$TARGET"
  grep -qE 'pom\.xml|build\.gradle' "$TARGET"
  grep -q 'go\.mod' "$TARGET"
  grep -qE 'pyproject\.toml|requirements\.txt' "$TARGET"
  grep -q 'htmx' "$TARGET"
}

@test "cd-test-architecture documents the missing-profile fallback phrase" {
  grep -q 'name the missing profile' "$TARGET"
}

@test "cd-test-architecture documents --stack within the Parse Arguments section" {
  # Slice the file from '## Parse Arguments' to the next '## ' heading,
  # then assert --stack appears in that block.
  section=$(awk '/^## Parse Arguments/{flag=1; next} /^## /{flag=0} flag' "$TARGET")
  echo "$section" | grep -q -- '--stack'
}

@test "cd-test-architecture states that --stack takes precedence over manifest detection" {
  # Range starts on the line AFTER the 'Detect stack' heading and ends at the
  # next '### ' heading. Two-stage awk avoids collapsing the range on the
  # heading line itself.
  block=$(awk '/^### .*Detect stack/{flag=1; next} /^### /{flag=0} flag' "$TARGET")
  echo "$block" | grep -qEi 'takes precedence|overrides|skips detection|wins over'
}

@test "cd-test-architecture target-architecture schema requires citing the loaded profile" {
  block=$(awk '/^### Target architecture/{flag=1; next} /^### /{flag=0} flag' "$TARGET")
  echo "$block" | grep -qEi 'cite.*profile|profile.*cite|test-stack-profiles'
}

@test "cd-test-architecture body contains no language-specific tokens (frontmatter/fences excluded)" {
  count=$(body_only < "$TARGET" | grep -Ec "$BANNED_TOKENS" || true)
  [ "$count" -eq 0 ]
}
