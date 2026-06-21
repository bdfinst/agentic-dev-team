# Ownership Engineering eval suite

A behavioral eval suite that scores this plugin's **team agents and workflow
skills** against the **Ownership Engineering** framework (Stan Chen): coding agents
should be optimized to *deliver outcomes* and *own results* like a senior engineer,
not to *avoid being wrong* like an assistant.

This is distinct from the deterministic detection corpus in `evals/expected/`. That
corpus grades *review agents* on whether they detect code issues, scored
model-free by `scripts/eval_grade.py`. This suite grades *behavior* — does an agent
investigate vs. escalate, decide vs. menu, prove vs. assert — which is inherently
judgment-based, so it is **judge-graded** (LLM-as-judge or human).

## Contents

| File | What it is |
| --- | --- |
| [`rubric.md`](rubric.md) | The eight scored dimensions (CW, UA, CD, ER, LV, DD, DC, QO), the 1–5 scale, and what exhibits/violates each. |
| [`scorecard.md`](scorecard.md) | Baseline assessment of each subject against the rubric, with file:line evidence (hand-authored provenance). |
| `fixtures/oe-*.md` | Behavioral scenarios. Each places a subject in a situation that probes one or more dimensions. |
| `expected/oe-*.json` | Per-fixture `mustExhibit` / `mustNotExhibit` behavior lists and the dimensions probed. |

## The eight dimensions

| Code | Dimension | One-liner |
| --- | --- | --- |
| CW | Clarification Window | Ask everything up front in one round, then commit. |
| UA | Uncertainty Absorption | Investigate to resolve unknowns; don't escalate every one. |
| CD | Committed Decisions | Decide and own it (with override); don't hand over a menu. |
| ER | Evidence Over Reasoning | Fresh observed output, not assertion. |
| LV | Live Validation | Run the real thing; static reading isn't proof. |
| DD | Debug, Don't Stop | A failure is a debugging task, not a hand-back. |
| DC | Demonstrable Completion | Done = proven working, not "code changed." |
| QO | Quality Ownership | A failing test is failure regardless of whose change caused it; own the suite, not just your delta. |

## Fixtures at a glance

| Fixture | Subjects | Dimensions |
| --- | --- | --- |
| `oe-01-vague-feature-request` | product-manager, orchestrator | CW, UA, CD |
| `oe-02-mid-build-unknown` | software-engineer | UA, DD, CD |
| `oe-03-two-viable-designs` | architect | CD, UA |
| `oe-04-done-without-evidence` | quality-gate-pipeline, build | ER, DC |
| `oe-05-ui-change-static-only` | qa-engineer, build | LV, ER, DC |
| `oe-06-failing-test-handback` | systematic-debugging, build | DD, ER |
| `oe-07-implementation-not-completion` | quality-gate-pipeline, qa-engineer, progress-guardian | DC, ER |
| `oe-08-medium-severity-escalation` | human-oversight-protocol | CD, UA |
| `oe-09-preexisting-failing-test` | build, quality-gate-pipeline, qa-engineer | QO, DC, ER |
| `oe-10-replace-vs-merge` | orchestrator, product-manager | CW, CD |
| `oe-11-no-instruction-yet` | orchestrator, context-loading-protocol | CW, UA |

## How to run / grade

These fixtures are behavioral, so grading is by judge rather than by
`eval_grade.py`. To evaluate a subject against a fixture:

1. Give the subject (an agent via `/review-agent`-style dispatch, or a skill driven
   on a sample task) **only** the fixture scenario — never the `expected/*.json`.
2. Capture its behavior (the questions it asks, whether it investigates, what it
   accepts as "done", what evidence it produces).
3. Apply the fixture's `expected/*.json`: a fixture **passes** only if every
   `mustExhibit` behavior is present **and** no `mustNotExhibit` behavior appears.
4. Score the probed dimensions 1–5 per the rubric and update the scorecard.

`oe-08` once carried `"knownGap": true` (the oversight prose mandated "present
options"). The [improvement plan](../../plans/ownership-engineering-improvements.md)
has since rewritten the Medium tier to decide-and-proceed-with-override, so the gap
is closed (`knownGap: false`) and `oe-08` now serves as the **regression sentinel**
guarding that behavior.

## Why this lives outside `evals/expected/`

The CI structural gate runs `eval_grade.py --check-corpus`, which globs
`evals/expected/*.json` (non-recursive) and requires each file to conform to the
detection schema (`applicableAgents`/`applicableSkills`, count/severity ranges).
These behavioral expecteds use a different, judge-oriented schema, so they live in
`evals/ownership-engineering/` to stay out of that gate — adding them under
`evals/expected/` would red-line the structural check. If a future deterministic
behavioral grader is built, point it at this directory explicitly with
`--expected-dir`.
