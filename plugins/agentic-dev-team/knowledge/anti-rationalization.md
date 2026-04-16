# Anti-Rationalization Patterns

LLMs generate plausible excuses for skipping process. If the excuse is not listed here, it is still an excuse. The absence of a pattern from this table does not grant permission to skip a gate.

For domain-specific rationalization tables, see:
- TDD: [Rationalization Prevention](../skills/test-driven-development/SKILL.md#rationalization-prevention)
- Debugging: [Rationalization Prevention](../skills/systematic-debugging/SKILL.md#rationalization-prevention)

## Cross-Cutting Patterns

| Category | Excuse | Reality | Common In |
|----------|--------|---------|-----------|
| Skipping verification | "I already verified this earlier in the conversation" | Earlier evidence is stale. Re-run and show current output. | Quality Gate Pipeline, TDD |
| Skipping verification | "The change is too small to need verification" | Small changes cause regressions. Run the gate. | Quality Gate Pipeline |
| Skipping tests | "This is just a config/docs change, no tests needed" | Config changes can break builds. Verify the config loads. | TDD, Quality Gate Pipeline |
| Skipping tests | "I'll add tests after the implementation is working" | Tests written after implementation confirm assumptions, not behavior. | TDD |
| Scope expansion | "While I'm here, I should also fix..." | Scope creep introduces unplanned risk. Finish the current task first. | All skills |
| Scope expansion | "This refactor is necessary to make the fix work" | If it was not in the plan, flag it to the orchestrator before proceeding. | Hexagonal Architecture, Legacy Code |
| Premature completion | "Should work now" / "Should be fixed" | "Should" is not evidence. Run verification and paste output. | Quality Gate Pipeline |
| Premature completion | "The logic is correct so the tests will pass" | Correctness is proven by execution, not reasoning. Run the tests. | TDD, Quality Gate Pipeline |
| Process shortcuts | "This is a trivial change, we can skip the cycle" | Trivial changes still require Phase 2 verification at minimum. | Quality Gate Pipeline, TDD |
| Process shortcuts | "The deadline is tight, so let's skip review" | Skipping review costs more time in rework. Follow the pipeline. | Quality Gate Pipeline |
