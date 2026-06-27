# BDD Value Guide — when Gherkin earns its keep

A reusable decision framework for whether BDD/Gherkin adds value or is ceremony
overhead. Use it to pick a **test-binding mode** for a feature or a whole repo,
instead of re-deriving the trade-off each time or leaving the operator unsupported.

The question is never "is Gherkin good?" — it is "does *this* code, with *this*
team and *these* readers, get more from executable specifications than it pays in
indirection?" BDD's value comes almost entirely from **collaboration and shared
language**, not from the test mechanics: an `xunit-with-annotations` test and a
`bdd-runner` scenario validate behavior equally well. Pay the runner's overhead
only when non-technical readers or collaborative authoring are real.

## Decision rubric

Answer five yes/no questions. Each "yes" is a signal toward a BDD runner.

| Question | BDD signal |
|---|---|
| Do non-developer stakeholders (PM, BA, QA, auditors) need to read or co-author these specifications? | Strong yes → `bdd-runner` |
| Are you specifying business domain behavior — not infrastructure, plumbing, or data transforms? | Strong yes → `bdd-runner` |
| Does the team practice collaborative spec authoring (three-amigos, story mapping)? | Yes → `bdd-runner` |
| Is there a living-documentation requirement — scenarios must remain the definitive spec and drift is a defect? | Yes → `bdd-runner` |
| Is there existing Gherkin in this repo? | Yes → match the pattern |

## Recommendation mapping

Count the "yes" answers and map to a binding mode:

| Score | Binding mode | Rationale |
|---|---|---|
| ≥ 3 yes | `bdd-runner` | Non-technical readers exist or collaboration is the point — the runner's living documentation pays for itself |
| 1–2 yes | `xunit-with-annotations` | Gherkin as structured documentation (Given/When/Then comments on xUnit tests) without runner ceremony |
| 0 yes | `none` | Plain xUnit — identical test quality, less overhead and indirection |

The three binding modes:

- **`bdd-runner`** — scenarios execute their Given/When/Then steps through the language's BDD runner (Cucumber.js, Cucumber-JVM, Reqnroll, Godog). The `.feature` file *is* the living spec.
- **`xunit-with-annotations`** — one xUnit-style test per scenario; the test name mirrors the scenario, and the Given/When/Then become structured comments citing the source `.feature` file. Readable, no runner dependency.
- **`none`** — ordinary xUnit tests named for behavior. Same defect-catching power; least ceremony.

## When Gherkin is almost always overkill

- **Pure technical layers** — utilities, data mappers, infrastructure adapters, serialization plumbing. No business reader will ever open these scenarios.
- **Small all-technical teams** — ≤ 4 developers with no non-developer stakeholders; the shared-language benefit has no audience.
- **Spike / prototype / short-lived code** — the spec will be thrown away before anyone reads it.
- **Internal tooling with no compliance requirement** — living documentation buys nothing.

In these cases choose `none` (or `xunit-with-annotations` if a scenario shape already exists). Adding a runner here is pure indirection for no reader.

## When it is almost always worth it

- **Regulated domain** — payments, healthcare, compliance-auditable financial rules. Auditors and domain experts must read and trust the spec; living documentation that drifts is a defect.
- **Shared-language gap** — developers and the business describe the same behavior differently, producing misaligned tests. Collaborative Gherkin authoring closes the gap before code is written.
- **Existing `.feature` files in the repo** — consistency wins; match the established pattern rather than splitting the suite across two styles.

In these cases choose `bdd-runner` and wire it per `bdd-frameworks.md`.

## See also

- `../test-stack-profiles/bdd-frameworks.md` — per-language wire-in (install, layout, runner config, step stubs) once you have chosen `bdd-runner`.
