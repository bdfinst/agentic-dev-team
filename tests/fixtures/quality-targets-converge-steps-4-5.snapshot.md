### 4. Pick the largest gap + dispatch the smallest action

Use this priority order (matches the spec's order of operations) when two gaps tie:

1. Determinism (a flaky suite invalidates every other metric).
2. Surviving mutants (coverage you can't trust isn't coverage).
3. Line + branch coverage.
4. Wall-clock (only if the operator set a target).

For the picked gap, dispatch the smallest action — by emitting a recommendation, not by editing code (the actual edit happens via `/build` against a Phase-5 Story):

| Gap | Smallest action |
|---|---|
| Flaky test | Identify the source of non-determinism (real clock, RNG, sleep, shared state, order dependence). Propose a Phase-5 Story to remove it. |
| Surviving mutant on a covered line | The test asserts coverage but not behavior; propose a Phase-5 Story to add the specific assertion that kills this mutant. |
| Surviving mutant on an uncovered line | Propose a Phase-5 Story to add a test that hits the line *and* asserts the behavior. |
| Coverage gap on a single file | Propose a Phase-5 Story to add a component test for the uncovered branch at the existing seam. If none exists, propose a paired `[Refactor-for-testability]`. |
| Wall-clock regression | Identify the slowest tests (top 10). Propose a Story to swap a local container for an in-memory double where both prove the behavior. |

**Gherkin binding for proposed component tests.** When the smallest action is "add a component test" (rows 2, 3, 4 above), first check `memory/test-modernize/<slug>/gherkin-bindings.json` for an approved Scenario covering that behavior at the relevant public surface:

- **Scenario exists** — the proposed Story extends the matching `[Component tests]` Story rather than creating a new one. The recommendation cites `<feature-file>::<scenario-name>` and the test added in `/build` binds to that scenario in the binding mode recorded in `phase-0.md`.
- **Scenario is missing** — do NOT invent a Scenario inside a Phase-5 Story (that would bypass the Phase-2 human gate). Open a `[Phase-2 amendment]` Story instead with title `[Phase-2 amendment] Add Scenario(s) to <feature-file>`, describing the behavior to specify, and pause the convergence loop until the operator approves the amendment via the standard Phase-2 sign-off. After the operator merges the new Scenario into the `.feature` file and updates `gherkin-bindings.json`, the convergence loop resumes and the component-test Story binds to the now-approved Scenario.

This keeps the approved Gherkin as the single source of intended behavior even when Phase 5 discovers a gap. The operator stays the only author of intent.

Each recommendation lands as a new child issue on the parent (via the same CLI dispatch convention as `/issues-from-assessment`) or as a new file under `./plans/test-modernize/phase-5/`. The orchestrator (`/test-modernize`) then drives `/build` against each.

### 5. Re-measure + decide whether to loop

After `/build` closes the dispatched Story:

- Re-measure (Step 2).
- If all four targets met → exit loop, mark Phase-5 close-out Story Done.
- If `--max-iterations` reached → halt, print current state, ask the operator to waive remaining gaps or extend.
- Otherwise → next iteration.

