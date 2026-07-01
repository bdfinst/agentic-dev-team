<!-- spec-version: 1 -->
# Spec: Farley Score honors --path / --since scope

Closes #533.

## Intent Description

`/test-design` currently computes the Farley Score over **every** test file in
the repository regardless of `--path` or `--since`. When `/test-health` (which
does honor `--path`) invokes `/test-design` on a subtree, the aggregated report
silently mixes a whole-repo headline number with subtree-scoped findings — the
two contradict each other and the user has no way to tell.

The fix is to make Farley Score follow scope in `/test-design`, label the score
with the scope it was computed over, and have `/test-health` pass its `--path`
through explicitly so the number matches the rest of the audit. Unscoped
invocations of `/test-design` are unchanged: whole-repo Farley, labelled
"all tests".

## Architecture Specification

Two skill files change; both are behavioral spec (Markdown consumed by the
model), no code paths.

Components touched:

- `plugins/dev-team/skills/test-design/SKILL.md` — Step 3 (Farley scoring) and
  the report header template in Step 6.
- `plugins/dev-team/skills/test-health/SKILL.md` — Step 6 (invocation of
  `/test-design`) and the report Output block.

Constraints:

- `/test-design` remains the single owner of Farley scoring; `/test-health`
  consumes it (per `test-health` Constraint 4, "No scoring reinvention"). This
  fix does not move scoring, it just makes the scope explicit.
- Score label vocabulary is exactly three strings — `all tests`,
  `under <path>`, `changed since <ref>` — so downstream summarizers can parse
  it deterministically.
- `farley-score` (the worker skill) is not touched. It scores whatever set of
  files it is handed; scope selection lives in the caller.
- Test-file selection uses the existing `knowledge/test-file-indicators.md`
  taxonomy — no new indicator logic.

No changes to CI, hooks, agent registry, or model routing.

## Acceptance Criteria

1. `/test-design` with no scope flag scores every test file in the repository
   and the report header reads `**Farley Score (all tests)**: ...`.
2. `/test-design --path <dir>` scores exactly the test files whose path is
   under `<dir>` **or** that exercise production code under `<dir>`, and the
   report header reads `**Farley Score (under <dir>)**: ...`.
3. `/test-design --since <ref>` scores exactly the test files touched in the
   diff plus the test files covering production files touched in the diff, and
   the report header reads `**Farley Score (changed since <ref>)**: ...`.
4. If the in-scope test set is empty, Step 3 is skipped and the report notes
   `no in-scope test files` in place of a score.
5. `/test-health --path <dir>` invokes `/test-design --path <dir>` (invocation
   string is explicit in the skill) and its rendered Farley Score line carries
   the `under <dir>` scope label.
6. `/test-health` with no `--path` invokes `/test-design` with no `--path` —
   suite-wide score, label `all tests`.
7. `tests/docs/test_design_skill_dispatch_tests.bats` and any other bats
   assertions over these two SKILL files pass unchanged or are updated in the
   same PR; `bash scripts/ci-local.sh` and `/agent-eval` both pass.

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
|---|---|---|---|
| Option 1 (score follows scope) vs Option 2 (opt-in flag) | `inferable` | inference | Issue #533 recommends Option 1; Option 2 adds surface area with no evidence of demand. |
| Exact label strings for the three scope modes | `inferable` | inference | Issue proposes `all tests` / `under <path>` / `changed since <ref>`; adopted verbatim so downstream parsing is deterministic. |
| Empty-scope behaviour (path/ref resolves to zero tests) | `inferable` | inference | Existing empty-suite branch already skips the step; extend the same "skip + note" path to empty in-scope sets. |
| Behaviour of `--path` pointing at a **file** (single-file → auto-`--advise`) | `inferable` | inference | Step 1 already special-cases single-file targets; Farley scope reuses the same target set — no separate rule needed. |
| Should `/test-health` render the scope label in its Output block? | `inferable` | inference | Constraint 4 forbids re-deriving the score, not re-rendering the label. Passing the label through is consistent with "consume, don't restate." |
| Farley-score worker skill (`plugins/dev-team/skills/farley-score/SKILL.md`) edit? | `inferable` | inference | The worker scores whatever file set it receives; scope selection belongs to the caller. No change. |

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts (scope labels fixed)
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — all `inferable` with rationale
