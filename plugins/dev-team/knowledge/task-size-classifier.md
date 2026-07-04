# Task Size Classifier

Objective task-size signal that feeds the `trivial | standard | complex` vocabulary
used by `/plan` (step 5a tier), `/build` (per-step review depth), and the
orchestrator's no-plan fast path. **Never re-classify using a fresh LLM judgement** —
derive the tier from the objective signals below.

Calibrated from `docs/experiments/agentic-workflow-evidence/data/3sizes-3arms-summary.json`.
Routing rationale: Rec 2 of `docs/experiments/RECOMMENDATIONS.md` — the full
pipeline's cost premium shrinks as tasks grow (4.74× small, 2.57× medium,
1.33× large), so small, well-specified work routes to direct single-agent
dispatch and the pipeline is reserved for large, multi-file work.

## Inputs

Collect these signals before classifying. When a signal is unavailable (e.g. no
plan yet exists), omit it and classify conservatively.

| Signal | How to obtain |
|--------|---------------|
| `files_changed` | `git diff --name-only HEAD` or the plan's slice file lists (deduplicated) |
| `loc_delta` | `git diff --stat HEAD \| awk '/files? changed/ {print $4+$6}'` — net insertions + deletions |
| `slice_count` | `plan-waves.sh` JSON `.slices \| length` — or 1 when no plan exists |
| `wave_count` | `plan-waves.sh` JSON `.waves \| length` — or 1 when no plan exists |
| `has_complex_step` | Any step in the plan with `**Complexity**: complex` |
| `decision_axis_triggered` | Any high-reversal-cost axis in `knowledge/decision-defaults.md` raised by this task (checked during discovery) |
| `single_module` | True when every changed file (from the plan's slice file lists, or `git diff --name-only HEAD`) lives in one module — a single top-level source directory/package plus its test mirror. False when files span modules or the file set is unknown. |

## Classification Rules

Apply in order; the first match wins.

### Trivial (no-plan fast path eligible)

**ALL** of the following must hold:

- `files_changed` ≤ 1
- `loc_delta` ≤ 50
- `slice_count` ≤ 1
- `wave_count` ≤ 1
- `has_complex_step` = false
- `decision_axis_triggered` = false  ← decision-axis guardrail: never skips plan for high-reversal-cost work

Expected saving vs full pipeline: ~65% fewer turns, ~45% lower cost (small-kata data; see calibration file).

### Complex

**ANY** of the following:

- `files_changed` ≥ 6
- `loc_delta` ≥ 300
- `wave_count` ≥ 2
- `has_complex_step` = true
- `decision_axis_triggered` = true
- Security-sensitive or cross-cutting concern (cross-module invariant, auth, data schema)

### Standard

Everything between trivial and complex.

## Route (1:1 with classification — this file is the single source of truth)

| Classification | Route |
|---|---|
| `trivial` | No-plan fast path |
| `standard`, **fast-path eligible** (below) | No-plan fast path |
| `standard`, otherwise | Full three-phase workflow |
| `complex` | Full three-phase workflow |

**Fast-path eligibility for `standard`** (Rec 2): a well-specified
single-module `standard` task routes to the no-plan fast path when **ALL** of
the following hold:

- `single_module` = true
- `slice_count` ≤ 1
- `has_complex_step` = false
- `decision_axis_triggered` = false  ← decision-axis guardrail: a triggered axis always excludes the fast path

Any exclusion failing — files spanning modules, more than one slice, any
`complex` step, or any triggered decision axis — sends the task to the full
three-phase workflow. When `single_module` cannot be determined, treat it as
false (bias rule below).

## Bias rule

When signals are ambiguous or a signal is missing, **classify up** (standard rather
than trivial, complex rather than standard). The fast path is an optimisation — the
cost of a false-trivial (wrong route, rework) is higher than the cost of a false-standard
(unnecessary planning).

## Decision log entry

After classifying, append to `memory/decisions.md`:

```
**ID**: DEC-<date>-SIZE
**Date**: <date>
**Agent**: orchestrator
**Task**: <task slug>
**Decision**: Classified as <trivial|standard|complex> → route <fast path|full workflow>
**Inputs**: files_changed=<N>, loc_delta=<N>, slice_count=<N>, wave_count=<N>, has_complex_step=<bool>, decision_axis_triggered=<bool>, single_module=<bool>
**Rationale**: <which rule fired>
```
