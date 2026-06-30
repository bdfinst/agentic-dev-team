#!/usr/bin/env bats
#
# Verifies the .NET smoke fixture and PR-body evidence draft for issue #524
# (Slice 4 of plans/stack-aware-reference-loading.md). Structural checks only —
# whether the LLM-produced excerpts are semantically correct is the human
# merge reviewer's call.

FIXTURE_DIR="evals/fixtures/dotnet-http-smoke"
PR_BODY="docs/pr-bodies/524.md"

@test "fixture directory exists and contains a .csproj" {
  [ -d "$FIXTURE_DIR" ]
  count=$(find "$FIXTURE_DIR" -maxdepth 2 -name '*.csproj' | wc -l)
  [ "$count" -ge 1 ]
}

@test "fixture contains at least one *Tests.cs file" {
  count=$(find "$FIXTURE_DIR" -maxdepth 2 -name '*Tests.cs' | wc -l)
  [ "$count" -ge 1 ]
}

@test "fixture's test file contains the deliberate Mock<HttpClient> smell" {
  # The fixture's whole point is to give /test-smell-review something to flag.
  # Without this line, the manual verification step's smell scenario is vacuous.
  found=$(grep -l -E 'Mock<HttpClient>|new Mock\(typeof\(HttpClient\)\)' "$FIXTURE_DIR"/*Tests.cs 2>/dev/null || true)
  [ -n "$found" ]
}

@test "fixture's client class accepts HttpClient as a constructor parameter" {
  # Defines the 'outbound HTTP code path' trigger from acceptance criterion A5.
  found=$(grep -l -E '\(HttpClient[[:space:]]+[a-zA-Z_]|\([[:space:]]*HttpClient[[:space:]]*\)' "$FIXTURE_DIR"/*.cs 2>/dev/null || true)
  [ -n "$found" ]
}

@test "PR body draft exists" {
  [ -f "$PR_BODY" ]
}

@test "PR body draft contains an Evidence heading" {
  grep -q '^## Evidence' "$PR_BODY"
}

@test "PR body draft cites the .NET stack profile path" {
  grep -q 'knowledge/test-stack-profiles/dotnet\.md' "$PR_BODY"
}

@test "PR body draft cites the C# HTTP-client reference path" {
  grep -q 'knowledge/references/csharp-http-client-testing\.md' "$PR_BODY"
}
