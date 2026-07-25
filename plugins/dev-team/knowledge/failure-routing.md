# Failure-Class Routing

Read at the start of each repair iteration in `/build` step 4 (per-behavior
cycle, review-fix loop) and `/apply-fixes` step 4 (per-fix validation).
Classify the failing output/exit code by regex — deterministic, no LLM call,
no extra dispatch. Only the route changes; iteration caps never rise and a
route switch never resets the shared budget.

## Classification Table

| Signature pattern | Class | Route | Escalation |
|---|---|---|---|
| `SyntaxError\|error TS\d+\|cannot find symbol\|ParseError\|unexpected token`; compiler exit 2 | `compile-syntax` | inline fix | Stays inline on repeat — no ambiguity left to diagnose. |
| Named test fails again after one inline attempt; `AssertionError\|expect\(.*\)\.to\|FAILED .*::test_` | `behavioral-test` | inline fix (1st time) | Same test fails again → systematic-debugging, not another blind retry. |
| `coverage.*below threshold\|Statements.*% \(< \|branch coverage .* below` | `coverage-gap` | test-generation (qa-engineer / test-improve-style) | Repeats → escalate to human (threshold may be miscalibrated). |
| `eslint\|prettier\|black --check\|ruff\|gofmt` non-zero, style-only diagnostics | `lint-format` | inline fix | Repeats → generic fall-through (likely config, not code). |
| Security-review finding (secrets, injection, auth bypass) surfaces during validation | `security-finding` | security-engineer (`/build`: dispatch, effort high; `/apply-fixes`: annotate only — no Agent/Skill grant) | Never downgrades to inline; unresolved after dispatch → human arbitration. |
| Two+ reviewers disagree on the same finding/fix | `reviewer-conflict` | human arbitration (existing escalation: interactive ask; non-interactive hard stop to `.claude/memory/build-escalation-<slug>.md`) | Never auto-resolved by picking a side. |
| No pattern matches | `unclassified` | generic loop (fall-through, unchanged) | None — identical to pre-routing behavior. |

## Notes

- `/build`: classification *is* the diagnosis step orchestrator constraint 7
  already requires — not an added step.
- `/apply-fixes` has no `Agent`/`Skill` grant: non-inline routes annotate the
  Fix Summary with class + recommended route and move on — never dispatch.
- A route switch (e.g. inline → systematic-debugging) spends from the same
  5-iteration cap / 2-correction-iteration checkpoint — never extends or resets it.
