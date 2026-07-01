#!/usr/bin/env bats
# Contract for the mutation-kill agent (epic #443, issue #461).
# An autonomous survivor-reduction loop: scoped tool -> survivors -> generate
# tests -> verify -> commit -> repeat, gated on hard kills only.

AGENT="$BATS_TEST_DIRNAME/../../plugins/dev-team/agents/mutation-kill.md"
REGISTRY="$BATS_TEST_DIRNAME/../../plugins/dev-team/knowledge/agent-registry.md"

@test "mutation-kill.md exists" {
  [ -f "$AGENT" ]
}

@test "declares the required frontmatter (name, description, tools, effort)" {
  fm=$(awk 'NR>1 && /^---/{exit} {print}' "$AGENT")
  echo "$fm" | grep -Eq '^name: *mutation-kill'
  echo "$fm" | grep -Eq '^description:'
  echo "$fm" | grep -Eq '^tools:'
  echo "$fm" | grep -Eq '^effort: *(low|medium|high)'
}

@test "agent body stays under the 500-line file limit" {
  [ "$(wc -l < "$AGENT")" -lt 500 ]
}

@test "defines the honest score formula (hard kills only, timeout excluded)" {
  grep -Eqi 'honest' "$AGENT"
  grep -Eq 'Killed */ *\(Killed \+ Survived \+ NoCoverage\)' "$AGENT"
  grep -Eqi 'timeout' "$AGENT"
  # Retired formula must be gone, not just supplemented.
  ! grep -Eq 'Killed */ *\(Total *- *Ignored' "$AGENT"
}

@test "reports timeout count separately and never gates on it" {
  grep -Eqi 'timeout.*separate|report.*timeout|never.*timeout|timeout.*not.*(count|gate)' "$AGENT"
}

@test "NoCoverage is a first-class signal, prioritized before hard Survived mutations" {
  # NoCoverage must appear in the formula, first-class-signal note, and prioritization guidance.
  [ "$(grep -c -F 'NoCoverage' "$AGENT")" -ge 3 ]
  grep -Eqi 'prioritize NoCoverage|NoCoverage.*before.*Survived|NoCoverage.*first' "$AGENT"
}

@test "loop starts with a fresh build; prohibits --no-build on mutation runs" {
  # The build-first step must precede the loop pseudo-code.
  grep -Eq 'dotnet build' "$AGENT"
  # The prohibition against --no-build during mutation runs must be explicit.
  # Flatten newlines so a line-broken sentence still matches.
  tr '\n' ' ' < "$AGENT" | grep -Eqi 'never.*--no-build|do not use.*--no-build|not.*--no-build'
}

@test "--parallel <n> is documented as an Invocation flag with Agent-tool fan-out" {
  # Invocation surface
  grep -Eq -- '--parallel' "$AGENT"
  # Parallel-execution section exists
  grep -Eqi '^## Parallel execution|^### Parallel execution' "$AGENT"
  # Agent tool, not worktrees
  grep -Eqi 'Agent tool' "$AGENT"
  # Batch cardinality claims from the plan's scenario
  grep -Eq '3.4' "$AGENT" || grep -Eq '3-4' "$AGENT"
  grep -Eq '1.2' "$AGENT" || grep -Eq '1-2' "$AGENT"
}

@test "--parallel and --concurrency interaction rule is specified" {
  # The interaction rule must reference both flags in the "Parallel execution"
  # section. Use sed to extract from the section header to the next top-level
  # (^## ) header, dropping the header itself so its own regex doesn't close
  # the range prematurely.
  sed -n '/^## Parallel execution/,/^## [^P]/p' "$AGENT" | grep -Eqi 'concurrency'
}

@test "infrastructure exclusion detection: thresholds, file patterns, and log format" {
  # Numeric thresholds
  grep -Eq '15%' "$AGENT"
  grep -Eq '50%' "$AGENT"
  # Filename patterns
  grep -Eq 'Startup\.cs' "$AGENT"
  grep -Eq 'Program\.cs' "$AGENT"
  grep -Eq '\*Filter\.cs' "$AGENT"
  grep -Eq '\*Middleware\.cs' "$AGENT"
  grep -Eq '\*Logger\*\.cs' "$AGENT"
  grep -Eq '\*HealthCheck\*\.cs' "$AGENT"
  grep -Eq '\*\.Designer\.cs' "$AGENT"
  # EXCLUDED log-line format is already asserted elsewhere; here just confirm
  # the infra-exclusion section references it.
  grep -Eqi 'EXCLUDED' "$AGENT"
}

@test "warns that shard and full-run scores are not comparable" {
  grep -Eqi 'shard' "$AGENT"
  grep -Eqi 'not comparable|never (mix|compare)|prohibit.*compar' "$AGENT"
}

@test "requires a specific value assertion (status-code-only cannot kill)" {
  grep -Eqi 'status.?code' "$AGENT"
  grep -Eqi 'specific value|value assertion|assert.*value' "$AGENT"
}

@test "has the mutation-type priority order table" {
  grep -Eqi 'priority' "$AGENT"
  grep -Eq 'String' "$AGENT"
  grep -Eq 'ObjectInit' "$AGENT"
  grep -Eqi 'Equality' "$AGENT"
  grep -Eqi 'Statement' "$AGENT"
}

@test "notes Statement/Block need a missing code path, not stronger assertions" {
  grep -Eqi 'Statement|Block' "$AGENT"
  grep -Eqi 'missing code path|new (test|code path)|not.*stronger assertion|not.*existing' "$AGENT"
}

@test "per-language translation table covers JS/TS, Java, C#, Go" {
  grep -Eqi 'Stryker' "$AGENT"
  grep -Eqi 'pitest' "$AGENT"
  grep -Eqi 'Stryker\.NET' "$AGENT"
  grep -Eqi 'go-mutesting' "$AGENT"
}

@test "duplicate method detection stops cleanly" {
  grep -Eqi 'duplicate' "$AGENT"
  grep -Eqi 'stop' "$AGENT"
}

@test "build + test verification gates insertion; reverts on failure" {
  grep -Eqi 'revert|git checkout --' "$AGENT"
  grep -Eqi 'build' "$AGENT"
}

@test "documents the no-improvement exit condition" {
  grep -Eqi 'no.improvement|survivors >= prev|>= prev_survivors|stop.*no.*decreas' "$AGENT"
}

@test "concurrency flag defaults to 2" {
  grep -Eq -- '--concurrency' "$AGENT"
  grep -Eqi 'default.*2|2 per' "$AGENT"
}

@test "documents structurally unkillable file exclusion with a reason" {
  grep -Eqi 'unkillable|structural guard|exclude' "$AGENT"
  grep -Eqi 'reason|document the exclusion' "$AGENT"
}

@test "catalogs three structurally untestable patterns: #if DEBUG, service-locator, pure DI" {
  # #if DEBUG / #if RELEASE
  grep -Eq '#if DEBUG|#if RELEASE' "$AGENT"
  # service-locator: HttpContext.RequestServices.GetService<T>
  grep -Eq 'HttpContext\.RequestServices' "$AGENT"
  grep -Eqi 'service.?locator' "$AGENT"
  # pure DI registration
  grep -Eq 'services\.AddX|builder\.Services\.AddX|services\.Add[A-Za-z]|AddX\(\)' "$AGENT"
  grep -Eqi 'DI registration|test.?startup|TestStartup|TestServer' "$AGENT"
}

@test "Go runs advisory (logs, does not commit)" {
  grep -Eqi 'advisory' "$AGENT"
  grep -Eqi 'does not commit|not commit|operator applies' "$AGENT"
}

@test "registered in agent-registry.md" {
  grep -q 'agents/mutation-kill.md' "$REGISTRY"
}
