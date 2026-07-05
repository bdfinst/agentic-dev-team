# 17. Single build cadence — remove the Classic TDD opt-in

Date: 2026-07-05

## Status

Accepted

## Context

`/build` shipped with two per-behavior cadences: **Code-First Small Batches**
(IMPLEMENT → TEST → REFACTOR, the default) and **Classic TDD** (RED → GREEN →
REFACTOR, an explicit opt-in via `--tdd` or a plan's `**Cadence**: tdd`
metadata line). The opt-in touched `/build`'s argument parsing and cadence
resolution (a dedicated precedence step), `/plan`'s plan-template metadata
field, `/ship`'s pass-through description, and the `test-driven-development`
skill's framing as the cadence `/build` dispatched into automatically.

`docs/experiments/05-final-results.md` (Experiment 5, the workflow
efficiency-frontier study) measured both cadences head-to-head on
quality-per-dollar, with n=24 cells/arm and bootstrapped standard errors tight
enough to call the ranking of the top two arms decisively (see
"Ranking ambiguity" in that document):

| Rank | Workflow | Harness arm | Cost/cell | Quality | Qual/$ |
|--:|---|---|--:|--:|--:|
| **1** | Code-First Small Batches (Single Agent) | `continuous-single` | $0.99 | 0.961 | **0.968** |
| **2** | Classic TDD | `tdd-refactor` | $1.59 | 0.966 | **0.608** |

Both arms are "cleanly separated — from each other and from every arm below
them"; the top-two ranking is not expected to reorder with more trials. The
key nuance, stated explicitly in `docs/experiments/RECOMMENDATIONS.md`: this
is **not a quality gap**. Classic TDD's raw quality score (0.966) is
statistically indistinguishable from Code-First Small Batches' (0.961) — the
efficiency gap is driven entirely by cost. Classic TDD is a legitimate,
`docs/experiments/RECOMMENDATIONS.md`-endorsed "reasonable second choice,
particularly if a team has process reasons to prefer test-first discipline,"
costing "~60% more per unit of work" for essentially the same maintainability
outcome (blast radius 39.7 LOC/change vs. 40.0 — statistically identical).

Given that framing, carrying both cadences as a live `/build` opt-in bought
the plugin:

- A second cadence-resolution code path (`/build` step 3.5: CLI flag vs. plan
  metadata vs. legacy-plan inference vs. default) that every future build
  change has to reason about and keep in sync across three skills
  (`build`, `plan`, `ship`) and a plan-template metadata field.
- A `test-driven-development` skill framed as something `/build` might
  auto-dispatch into based on a flag or metadata, when in practice no plan in
  this repository's own history has opted in, and the experiment gives no
  efficiency reason to.
- Duplicated hard-gate logic (RED's failing-test gate, GREEN's passing-test
  gate) that mirrors Code-First Small Batches' TEST-phase gate almost
  exactly, for a cadence the data says costs ~60% more per cell for no
  measurable quality gain.

None of this argues Classic TDD is inferior craftsmanship — it ranked a
clean, statistically defensible #2 of 7 arms tested, well clear of every
big-batch workflow. It argues that maintaining it as a live, dual-path build
cadence is not worth the ongoing coordination cost when the plugin's own
experiment shows one cadence dominates on the metric (quality-per-dollar)
`/build` is designed to optimize for.

## Decision

Remove the Classic TDD opt-in from the build workflow. `/build` runs exactly
one cadence — Code-First Small Batches (IMPLEMENT → TEST → REFACTOR) — with
no `--tdd` flag, no plan `**Cadence**:` metadata field, and no
cadence-resolution precedence step. Concretely:

- `/build`: drop the `--tdd` argument, the dual-cadence description language,
  and the cadence-resolution step (formerly step 3.5). The per-behavior cycle
  section describes IMPLEMENT → TEST → REFACTOR only.
- `/plan`: drop the `**Cadence**: tdd` opt-in mention and the plan-template's
  `**Cadence**:` metadata field and its RED/GREEN/REFACTOR labeling
  alternative.
- `/ship`: drop the "TDD opt-in" phrase from its build-phase description.
- `test-driven-development` skill: reframed as an **advisory methodology
  reference**, not a build cadence toggle. It documents Classic
  RED-GREEN-REFACTOR discipline with its hard gates for a human who
  explicitly wants test-first discipline outside of `/build`, or for
  after-the-fact discipline audits. `/build` never dispatches into it
  automatically.
- `agents/qa-engineer.md`, `agents/software-engineer.md`: updated to describe
  `test-driven-development` as an advisory, on-request skill rather than a
  cadence `/build` selects via a flag or plan metadata.

Existing plans authored with `**Cadence**: tdd` metadata are unaffected
retroactively — this is a forward-only removal from the skill surface, not a
migration of historical plan files.

## Consequences

- One cadence-resolution code path instead of two: `/build` step numbering
  simplifies (no step 3.5), and every future build change reasons about a
  single per-behavior cycle.
- `test-driven-development` remains available and undiminished in rigor for
  anyone who wants Classic TDD discipline — it is now explicitly a
  human-invoked methodology reference, consistent with how the plugin treats
  other advisory skills (e.g. `legacy-code`, `mutation-testing`).
- This is a **cost-driven simplification, not a quality claim** — Classic TDD
  ranked a clean #2 of 7 arms with statistically indistinguishable
  maintainability to the winner. A team that has process reasons to prefer
  test-first discipline can still get it by invoking
  `test-driven-development` directly; they lose only the flag/metadata
  shortcut into `/build`, not the discipline itself.
- If a future, larger-corpus run of Experiment 5 (see "Future work" in
  `docs/experiments/05-final-results.md`) shows Classic TDD closing the
  cost gap or `/build`'s own users want test-first discipline as a
  first-class cadence again, that is a new decision to make with new
  evidence — this ADR does not preclude reintroducing an opt-in later.
