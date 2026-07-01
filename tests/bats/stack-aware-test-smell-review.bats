#!/usr/bin/env bats
#
# Verifies that plugins/dev-team/agents/test-smell-review.md is wired for
# stack-aware reference loading per plans/stack-aware-reference-loading.md
# (Slice 1, issue #524).
#
# Pattern source: plugins/dev-team/skills/test-design-advisor/SKILL.md:31, 62.
# The banned-token list and body_only() helper are duplicated across the
# stack-aware-*.bats files (one per target); if a fourth target adopts the
# pattern, extract them to tests/bats/_helpers/stack-aware.bash.

TARGET="plugins/dev-team/agents/test-smell-review.md"

# BANNED_TOKENS: language-specific tokens that must NOT appear in skill/agent
# body prose. Frontmatter and fenced code blocks are excluded by body_only().
# Mirrored in tests/bats/stack-aware-cd-test-architecture.bats and
# tests/bats/stack-aware-test-modernize.bats — keep in sync.
# Bare 'C#' and '.NET' are deliberately excluded: they appear in legitimate
# language-list contexts (e.g. naming which language test-file indicators
# the agent supports). The four tokens below only appear in language-specific
# guidance, so they discriminate cleanly.
BANNED_TOKENS='csharp|dotnet|HttpClient|HttpMessageHandler'

# body_only — strip YAML frontmatter delimited by --- markers and triple-backtick
# fenced code blocks from <stdin>, emit the prose body. Used for negative-grep
# assertions that must ignore language names appearing in worked examples or
# frontmatter `cites:` lists.
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

@test "test-smell-review names test-stack-profiles as a load-on-match knowledge source" {
  run grep -c 'test-stack-profiles' "$TARGET"
  [ "$status" -eq 0 ]
  [ "$output" -ge 1 ]
}

@test "test-smell-review cross-references test-design-advisor as the pattern source" {
  run grep -c 'test-design-advisor' "$TARGET"
  [ "$status" -eq 0 ]
  [ "$output" -ge 1 ]
}

@test "test-smell-review lists all six manifest tokens for stack detection" {
  grep -q 'package\.json' "$TARGET"
  grep -qE '\.csproj' "$TARGET"
  grep -qE 'pom\.xml|build\.gradle' "$TARGET"
  grep -q 'go\.mod' "$TARGET"
  grep -qE 'pyproject\.toml|requirements\.txt' "$TARGET"
  grep -q 'htmx' "$TARGET"
}

@test "test-smell-review documents the missing-profile fallback phrase" {
  run grep -c 'name the missing profile' "$TARGET"
  [ "$status" -eq 0 ]
  [ "$output" -ge 1 ]
}

@test "test-smell-review body contains no language-specific tokens (frontmatter/fences excluded)" {
  count=$(body_only < "$TARGET" | grep -Ec "$BANNED_TOKENS" || true)
  [ "$count" -eq 0 ]
}
