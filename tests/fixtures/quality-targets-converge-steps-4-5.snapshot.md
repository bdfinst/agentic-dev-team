### 4. Pick the largest gap + dispatch the smallest action

Use this priority order (matches the spec's order of operations) when two gaps tie:

1. Determinism (a flaky suite invalidates every other metric).
2. Surviving mutants (coverage you can't trust isn't coverage).
3. Line + branch coverage.
4. Wall-clock (only if the operator set a target).

For the picked gap, dispatch the smallest action — by emitting a recommendation, not by editing code (the actual edit happens via `/build` against a downstream Story):

| Gap | Smallest action |
|---|---|
| Flaky test | Identify the source of non-determinism (real clock, RNG, sleep, shared state, order dependence). Propose a downstream Story to remove it. |
| Surviving mutant on a covered line | The test asserts coverage but not behavior; propose a downstream Story to add the specific assertion that kills this mutant. |
| Surviving mutant on an uncovered line | Propose a downstream Story to add a test that hits the line *and* asserts the behavior. |
| Coverage gap on a single file | Propose a downstream Story to add a component test for the uncovered branch at the existing seam. If none exists, propose a paired `[Refactor-for-testability]`. |
| Wall-clock regression | Identify the slowest tests (top 10). Propose a Story to swap a local container for an in-memory double where both prove the behavior. |

**Gherkin binding for proposed component tests.** When the smallest action is "add a component test" (rows 2, 3, 4 above), first check `memory/<workflow>/<slug>/gherkin-bindings.json` for an approved Scenario covering that behavior at the relevant public surface:

- **Scenario exists** — the proposed Story extends the matching `[Component tests]` Story rather than creating a new one. The recommendation cites `<feature-file>::<scenario-name>` and the test added in `/build` binds to that scenario in the binding mode recorded in `phase-0.md`.
- **Scenario is missing** — do NOT invent a Scenario inside a downstream Story. Pause the convergence loop and hand back to the orchestrator: the operator remains the single author of intent, and the Gherkin surface must be updated via the workflow's standard Phase-2 sign-off before this loop resumes. Do not open ad-hoc amendment Stories from inside this worker; that route would bypass the human gate and is intentionally not available here.

This keeps the approved Gherkin as the single source of intended behavior even when convergence discovers a gap. The operator stays the only author of intent.

Each recommendation lands as a new child issue on the parent (via the same CLI dispatch convention as `/issues-from-assessment`) or as a new file under `./plans/<workflow>/phase-5/`. The orchestrator then drives `/build` against each.

### 5. Re-measure + decide whether to loop

After `/build` closes the dispatched Story:

- Re-measure (Step 2).
- If all four targets met → exit loop, mark the close-out Story Done.
- If `--max-iterations` reached → halt, print current state, ask the operator to waive remaining gaps or extend.
- Otherwise → next iteration.

