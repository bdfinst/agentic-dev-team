# 44. Critic stage for the review-fix loop

Date: 2026-11-22

## Status

Rejected. The critic was built, measured, and removed.

Tracked in [#2376](https://github.com/bdfinst/agentic-dev-team/issues/2376).

## Context

`/code-review` step 6a auto-applies every `error` or `warning` finding at `high` or `medium` confidence. The only check on a finding is the reporting agent's own Self-Challenge pass, so the same context grades its own work. A false positive costs a fix, a test run, and a re-dispatch.

## Proposal

An opt-in step 5d. A read-only `finding-critic` agent (opus, effort high) tries to refute each actionable finding before step 6a acts. A script accepts a refutation only when its quote is found within 3 lines of the cited line in the named file. A refuted `warning` is demoted, and a refuted `error` gets one rebuttal dispatch to its reporting agent. A flag, default `off`, enables it.

## Evaluation result

Measured 2026-11-24 over the 24 `*-review` lenses, 193 fixture pairs, one trial each. "Unexpected" is a heuristic: a finding that matches no `mustMention` term, or, on fixtures without one, falls beyond `issueCount.max`. Some unexpected findings may be real defects the fixtures do not list.

| Measure | Result |
| --- | --- |
| Baseline: unexpected share of actionable findings | 98 / 266 (36.8%) |
| True-positive loss (expected findings refuted) | 3 / 168 (1.8%) |
| False-positive catch (unexpected findings refuted) | 10 / 98 (10.2%) |
| Evidence rejection (quote failed the file check) | 0 / 13 |
| Critic cost | about $0.20 per fixture on opus |

The critic is accurate when it refutes: every quote was real and true-positive loss is within the 2% limit. It refutes too little to pay for the dispatch: 13 of 266 findings, about 4% of actionable noise removed. Loop replay was not run, because the catch rate leaves no room for a measurable gain in rounds or tokens.

Limits: the critic judged whole fixtures because baseline findings carry no line numbers, and findings were batched per fixture, not per round.

## Decision

Do not ship a critic stage. The implementation is removed from the tree.

Reopen only if a lens-level change makes a critic's catch rate material. Fixing the noisiest lenses at the source is the cheaper path: `js-fp-review`, `test-review`, `naming-review`, `claude-setup-review`, and `token-efficiency-review` produced 59 of the 98 unexpected findings.

## Consequences

- `/code-review` and `/build` are unchanged from before the proposal.
- No new agent, script, flag, or telemetry field.
