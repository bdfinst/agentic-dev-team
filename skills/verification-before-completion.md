---
name: verification-before-completion
description: Require fresh tool output as evidence before any completion claim. Use this skill at the delivery step of every agent — before saying "done", "complete", "finished", or presenting final output. Prevents the common LLM failure mode of claiming success without running tests or verifying output. Also use when reviewing another agent's completion claim.
role: worker
user-invocable: true
---

# Verification Before Completion

## Overview

LLMs confidently claim "done" without verification. This skill requires concrete evidence — fresh tool output from the current session — before any agent can mark work as complete. Trust tool output, not self-assessment.

## Iron Law

**No completion claims without fresh verification evidence.** Skipping any step of the gate function is falsification, not verification.

## Constraints
- Do not claim completion without fresh verification evidence from this session
- Do not reference test results or tool output from earlier in the conversation — re-run and show current output
- Do not substitute reasoning or explanation for actual evidence
- Do not mark a task complete if any verification step produces unexpected results
- Do not trust agent reports — inspect the actual output independently

## The Gate Function

Before making any completion claim, follow this five-step sequence. Skipping any step means the claim is unverified.

1. **IDENTIFY** — What command proves your claim? (e.g., `npm test`, `cargo build`)
2. **RUN** — Execute the command fresh and completely. Not from cache, not from memory.
3. **READ** — Read the complete output and exit code. Don't skim.
4. **VERIFY** — Does the output actually confirm your claim? If not, report the actual status.
5. **ONLY THEN** — Make the claim, with the supporting evidence pasted.

## Required Evidence (all tasks)
1. **Tests pass**: Run the test suite. Paste the output showing pass/fail counts. Stale results (from before your changes) don't count.
2. **Build succeeds**: If the project has a build step, run it. Paste the output.
3. **Lint clean**: If the project has a linter, run it. Paste the output.
4. **No regressions**: The test count should not decrease. If you removed tests, explain why.

## Required Evidence (by task type)
| Task Type | Additional Evidence |
|-----------|-------------------|
| Bug fix | Show the bug reproduced (failing test), then show it fixed (passing test) — red-green cycle |
| New feature | Show the feature working via test output or a demo command |
| Refactor | Show identical behavior: same test count, same pass count |
| Config change | Show the config loads without error |
| Documentation | Show the commands or code blocks in the doc actually work |
| Agent work | Inspect the VCS diff independently — do not trust the agent's self-report |

## Evidence Format
```
## Verification
- Tests: `npm test` → 47 passed, 0 failed (output below)
- Build: `npm run build` → success, 0 warnings
- Lint: `npm run lint` → 0 errors, 0 warnings
- Feature: `curl localhost:3000/api/health` → {"status":"ok"}
```

Paste actual tool output, not summaries. If the output is long, paste the relevant section with clear indication of what was run.

## Red Flag Language

Stop and verify when you notice yourself using:
- "should work now" / "should be fixed"
- "probably" / "likely" / "I believe"
- Expressing satisfaction before running verification
- Preparing commits or PRs without verification output
- Trusting a subagent's success report without checking
- "Just this once" / fatigue-based shortcuts
- Accepting partial checks as full verification (lint pass ≠ test pass)

These phrases signal you're about to claim completion without evidence. Run the gate function.

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "The tests were passing earlier" | Earlier is not now. Your changes may have broken something. Run them again. |
| "I can tell from the code that it works" | You can't. That's what tests are for. |
| "Running the tests would take too long" | Finding the bug in production takes longer. |
| "There are no tests for this area" | Then write a smoke test. Zero evidence is not acceptable. |
| "The changes are trivial" | Trivial changes cause non-trivial failures. Verify anyway. |
| "The linter passed, so it's fine" | Linter pass ≠ correctness. Run the actual tests. |
| "The agent said it worked" | Agent reports are claims, not evidence. Inspect the output yourself. |

## Integration
- Every agent applies the gate function before marking work complete
- The orchestrator verifies evidence is present before accepting Phase 3 output
- `/code-review` output includes a verification section by convention

## Output
Verification evidence block with tool output for each applicable check. If any check fails, the task is not complete — fix and re-verify.
