---
name: ci-debugging
description: Systematic CI/CD failure diagnosis with hypothesis-first approach, environment delta analysis, and anti-patterns. Use when CI fails, pipelines break, or the user says "CI is failing", "build broke", "pipeline error", or "tests pass locally but fail in CI".
role: worker
user-invocable: true
---

# CI Debugging

## Overview

CI failures are diagnosed systematically, not by guessing. This skill prevents the common anti-pattern of "just re-run it" by enforcing a hypothesis-first approach.

## Constraints

- Never suggest "retry the build" as a first action
- Never add retry logic to "fix" a flaky test
- Never push a speculative fix without reproducing locally first
- Always form a hypothesis before making changes

## Process

### 1. Read the failure

Read the full CI log output. Identify:
- **What failed**: test, lint, typecheck, build, deploy, or infrastructure
- **When it started failing**: this commit, recent merge, or intermittent
- **Error message**: exact error text, not a summary

### 2. Form a hypothesis

Before touching any code, state a hypothesis: "I believe X is failing because Y, and I can verify by Z."

Good hypotheses are specific and falsifiable:
- "The test fails because the database migration added a NOT NULL column and the test fixture doesn't set it"
- "The build fails because Node 20 dropped support for this API and CI upgraded last week"

Bad hypotheses:
- "Something is wrong with the tests"
- "CI is flaky"

### 3. Environment delta analysis

Compare local vs CI environments using this checklist:

| Factor | Check |
|--------|-------|
| **Runtime version** | Node, Python, Go, JDK, Ruby, .NET — exact version match? |
| **OS and architecture** | macOS vs Linux, x86 vs ARM? |
| **Dependency resolution** | Lockfile committed? Registry differences? Private packages accessible? |
| **Environment variables** | All required vars set? Secrets populated? |
| **Parallelism** | Tests run in parallel in CI but serial locally? Shared state? |
| **Memory/CPU** | CI runner constrained? OOM killer? |
| **Network** | External service dependencies? DNS resolution? Firewall rules? |
| **Filesystem** | Case sensitivity (macOS vs Linux)? Temp directory permissions? Path length? |
| **Timezone/locale** | Date formatting tests? Locale-dependent string comparisons? |
| **Docker** | Image tag `latest` drifted? Layer cache stale? Build context different? |

### 4. Reproduce locally

Before fixing, reproduce the failure locally:
1. Match the CI environment as closely as possible (same Node version, same env vars)
2. Run the exact failing command from the CI log
3. If it passes locally, the delta from step 3 is the cause

### 5. Fix and verify

Fix the root cause. Verify the fix locally. Push and confirm CI passes.

## Anti-Patterns

| Anti-pattern | Why it's wrong | What to do instead |
|-------------|---------------|-------------------|
| Retry the build | Masks the root cause, wastes CI minutes | Read the logs, form a hypothesis |
| Add retry/sleep to test | Hides race conditions, makes tests slow | Fix the shared state or ordering issue |
| Skip the failing test | Reduces coverage, hides regressions | Fix the test or the code |
| Push a speculative fix | Pollutes git history, might not work | Reproduce locally first |
| Blame "flaky CI" | Normalizes unreliable pipelines | Every failure has a cause — find it |

## Integration

- **DevOps/SRE Engineer agent**: Collaborates on infrastructure-level CI issues
- **QA Engineer agent**: Collaborates on test isolation and fixture problems
- **Systematic Debugging skill**: Uses the same hypothesis-first methodology
