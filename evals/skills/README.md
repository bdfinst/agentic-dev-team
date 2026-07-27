# Skill behavior specs (`.feature`)

These Gherkin `.feature` files are the **Given/When/Then behavior specs** for the
mutation-testing workflow skills shipped in the per-Story mutation probe
(plan: [`plans/mutation-testing-every-phase.md`](../../plans/mutation-testing-every-phase.md),
issues #283–#287). They exist for strict acceptance-criteria traceability: each
slice's AC named a `.feature` spec, and this directory is where they live.

## Why these are specs, not eval-grader fixtures

The deterministic eval grader (`scripts/eval_grade.py` + `scripts/eval_graders/`)
scores a single agent's or skill's **output** against an expected JSON, using a
registered grader genre (`verdict`, `skill_gate`, `integration`). The
mutation/coverage skills here are **workflow/orchestration contract skills**:
they have no analyzable output to score against a grader genre — their contract
is the text of the SKILL.md (flags, status enums, halt-prompt wording, atomic
writes). That contract is enforced executably by **bats** suites under
`tests/skills/`, which is also exactly what the plan's slice files specify.

Dropping these into `evals/expected/*.json` would either break
`--check-corpus` (no paired fixture, no applicable grader) or force a new grader
the plan explicitly deferred. So the spec and its enforcement are split:

| Behavior spec (`.feature`)                                    | Executable enforcement (`tests/skills/*.bats`)              | Issue |
| ------------------------------------------------------------- | ----------------------------------------------------------- | ----- |
| `mutation-testing/scoping.feature`                            | `mutation_testing_scoping_tests.bats`                       | #284  |
| `coverage-delta/mutation-delta.feature`                       | `coverage_delta_mutation_tests.bats`                        | #285  |
| `test-modernize/phase-4-mutation.feature`                     | `test_modernize_phase_4_mutation_tests.bats`                | #286  |
| `quality-targets-converge/mutation-reuse.feature`             | `quality_targets_converge_mutation_reuse_tests.bats`        | #287  |

## Keeping them honest

Each `.feature` carries an `# Enforced by:` header naming its executable
contract — `tests/skills/<name>.bats`, `tests/skills/<name>.py`, or (per this
repo's own established convention of placing agent-frontmatter content-guard
tests under `tests/agents/`, issue #1463) `tests/agents/<name>.py`.
[`tests/repo/test_feature_spec_refs.py`](../../tests/repo/test_feature_spec_refs.py)
asserts that header is present and points at a file that exists (and is
non-empty), so a spec can't silently drift from (or outlive) the suite that
enforces it.
