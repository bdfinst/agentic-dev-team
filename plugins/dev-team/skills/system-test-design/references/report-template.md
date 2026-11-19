# Report template

Write the report to `.dev-team-reports/system-test-design-<entry>.md`. Header, then these sections in order. A present section with no findings says so in one line. Every finding cites `path:line` or a test name and is labelled `observed` or `inferred`.

1. **Scope** — repos read, each `named` or `discovered`; `not scanned` deployables; alias map; mode; external boundaries; commit. A deployable the entry repo depends on that is unavailable is an external boundary, listed under Open questions. Which repos had coverage or mutation evidence.
2. **System map**
3. **Entangled workflows** — Workflow · Kind (shared table or schema / entangled value object / lockstep deployment) · Deployables · Evidence · Guarding E2E (candidate number or existing test) · Decoupling step.
4. **Current test architecture** — Suite · Path · Test type · Evidence for the type · Band (in band / out of band) · Pipeline stage (pre-merge, post-merge, acceptance, post-deploy, scheduled, production monitoring) · Blocks merge or deploy. Then pipeline findings: in-band tests calling shared or external services; non-deterministic tests blocking a merge or deploy. Descriptive counts per suite are allowed here, never targets.
5. **Test-double validation** — Test double · Dependency · Used by · Contract test · Integration test. A missing contract or integration test is a finding.
6. **Existing E2E triage** — Test · Class · Reason · Target layer and covering test.
7. **Minimum E2E set** — journeys with provenance per repo.
8. **Recommended E2E candidates** — per candidate: Type (critical business flow / entangled workflow / both; an entangled one names its workflow and says temporary) · Flow · Failure it detects (and why no other type can) · Impact · Assert (business outcome only) · Do not assert (with the owning or recommended test) · Placement (with reason) · Environment and test data (ephemeral environment; how the test creates and removes its data) · Async handling (poll condition, bounded wait) · Evidence.
9. **Rejected candidates** — Candidate · Reason · Owning test type and test.
10. **Overlap and misplacement** — Test · Behavior · Also asserted by · Owning type · Action (remove / remove the assertion / move to a type / merge).
11. **Contract-test findings** — business-logic leaks with fix; missing contract tests, missing provider verification, hand-crafted doubles, missing pipeline gates.
12. **Test improvements** — gaps (behaviors with no owning test); antipatterns from `test-layer-ownership.md` with the fix.
13. **Open questions**

## Mode omissions

The heading is absent, never "not run". Scope states the mode.

- `--e2e-only` omits *Overlap and misplacement* and *Test improvements*.
- `--overlap-only` omits *System map*, *Entangled workflows*, *Existing E2E triage*, *Minimum E2E set*, *Recommended E2E candidates*, and *Rejected candidates*.
- *Test-double validation* and *Contract-test findings* appear in every mode.

Last line: `Recommendations only; no tests were changed.`
