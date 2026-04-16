---
name: systematic-debugging
description: Four-phase debugging protocol (reproduce, investigate, root-cause, fix) that prevents guess-and-fix thrashing. Use this skill whenever a test fails, a bug is reported, an error occurs during implementation, or any unexpected behavior is encountered. Prevents the common LLM failure mode of guessing at fixes without understanding the problem.
role: worker
user-invocable: true
---

# Systematic Debugging

## Overview

When LLMs hit failures, they tend to guess at fixes — changing code, re-running, changing more code. This thrashing wastes context and often makes things worse. This skill enforces a four-phase protocol that requires understanding before action. Systematic debugging resolves issues in 15-30 minutes; guess-and-fix typically takes 2-3 hours with a 40% first-attempt success rate vs 95% systematic.

## Iron Law

**Find root cause before attempting fixes. Symptom fixes are failure.** No fixes without root cause investigation first.

## Constraints
- Do not change code until you have a root cause hypothesis
- Do not apply more than one fix at a time
- Do not skip the reproduction step — a bug you can't reproduce is a bug you can't verify as fixed
- Do not guess. Investigate.
- After 3+ failed fix attempts, question the architecture — stop patching

## The Four Phases

### Phase 1: Reproduce
**Goal**: See the failure with your own eyes (tool output).

1. Run the failing test or trigger the error condition
2. Read error messages thoroughly — don't skim. Stack traces contain line numbers, file paths, and often the solution.
3. Identify the minimal reproduction — strip away everything unrelated
4. Determine if the issue is consistent or intermittent
5. **Gate**: paste the reproduction output. If you can't reproduce it, gather more data — don't speculate.

### Phase 2: Investigate & Pattern Analysis
**Goal**: Gather facts and find working reference points.

**Investigate** (use as many techniques as needed):
- **Read the error**: Parse the stack trace. What file, line, and function? What's the actual error type?
- **Trace the data flow**: Follow the input from entry point to failure point. Where does the actual value diverge from the expected value?
- **Check recent changes**: What changed since this last worked? (`git diff`, `git log`)
- **Add observation points**: Temporary logging or print statements at key points to see actual values
- **Multi-component systems**: Add diagnostics at each component boundary — log data entering and exiting each layer to find which layer fails
- **Bisect**: If the failure surface is large, narrow it down by testing midpoints

**Pattern Analysis**:
- **Find working examples**: Locate similar functioning code in the same codebase
- **Compare against references**: Read reference implementations completely — don't skim
- **Identify differences**: List every distinction between working and broken code, no matter how minor
- **Understand dependencies**: What components, settings, and assumptions are required?

### Supporting References

Load these on demand when a specific technique is needed:

- **[Root-Cause Tracing](root-cause-tracing.md)** — When the failure involves a wrong value at the point of use. Trace backward through the call chain to find where the value first diverges.
- **[Condition-Based Waiting](condition-based-waiting.md)** — When debugging a flaky test that uses arbitrary sleeps or timeouts. Replace with polling.
- **[Find Polluter](find-polluter.md)** — When a test passes in isolation but fails in suite. Bisect the test list to find the polluting test.

**Gate**: state what you know and don't know. List the facts, not guesses.

### Phase 3: Root Cause Hypothesis
**Goal**: Identify the single underlying cause using the scientific method.

1. Form a single hypothesis: "I think X is the root cause because Y"
2. Predict what you would see if the hypothesis is correct (a test you haven't run yet)
3. Run that prediction test — make the smallest possible change, one variable at a time
4. If the prediction fails, your hypothesis is wrong — return to Phase 2 with new information
5. Do not compound fixes — test one hypothesis at a time
6. **Gate**: state the root cause in one sentence. If you can't, you don't have it yet.

### Phase 4: Fix
**Goal**: Make the smallest change that addresses the root cause.

1. Write or modify a test that captures the bug (it should fail now)
2. Apply the fix — one change, targeting the root cause
3. Run the test — it should pass
4. Run the full suite — no regressions
5. **Gate**: paste the test output showing the fix works and nothing else broke

**If the fix doesn't work**: Stop and reassess. After fewer than 3 attempts, return to Phase 1. After 3+ failures, question the architecture itself — when each fix reveals new problems elsewhere, the bug is architectural, not local. Discuss fundamentals with the human before attempting more fixes.

## Red Flags Requiring Process Restart

Stop immediately and return to Phase 1 if you notice:
- Planning "quick fix for now, investigate later"
- Attempting changes without understanding why they'd work
- Adding multiple modifications simultaneously
- Skipping testing in favor of "just checking manually"
- Fixing without investigation
- Not understanding something but proceeding anyway
- Adapting patterns differently than reference implementations
- Proposing solutions before tracing data flow
- Attempting a fourth or subsequent fix on the same issue
- Each fix revealing new problems in different locations

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "I think I know what's wrong, let me just try this" | That's guessing. Investigate first — it takes less time than three wrong guesses. |
| "The fix is obvious from the error message" | Then it'll be fast to verify your hypothesis before coding. Do it. |
| "I'll just try a few things and see what sticks" | Each attempt burns context and may introduce new bugs. One investigated fix beats five guesses. |
| "This is probably a race condition / timing issue" | "Probably" isn't a root cause. Add observation points and prove it. |
| "Let me revert everything and start over" | You'll hit the same bug again. Understand it first, then decide whether to revert. |
| "It's a simple issue, I don't need the full process" | Root causes exist in simple bugs too. The process handles simple issues quickly — just do it. |
| "We're under time pressure, just fix it fast" | Systematic debugging actually beats guess-and-check even under time pressure. |
| "Try fixing first, investigate if it doesn't work" | How you start establishes the pattern. Start correctly. |
| "Multiple simultaneous fixes save time" | You can't isolate what worked. You'll create new bugs. One fix at a time. |
| "I can see the problem, the cause is obvious" | Symptoms differ from root causes. What you see is the symptom. Investigate the cause. |

## Success Indicators

| Phase | You're Doing It Right When... |
|-------|-------------------------------|
| Reproduce | You have consistent reproduction with exact error output |
| Investigate | You can list facts (not guesses) about what's happening and have working reference code |
| Root Cause | You have a confirmed or revised hypothesis with prediction test results |
| Fix | Issue is resolved with a passing test and no regressions |

## When to Use This Skill
- A test that was passing now fails
- An error occurs during implementation
- Unexpected behavior is observed
- A bug report comes in
- A fix you applied didn't work (re-enter at Phase 2)
- You're under time pressure (especially then)

## Output
Root cause analysis with evidence: reproduction output, investigation findings, root cause statement, fix applied, and verification output showing the fix works without regressions.
