# Task Size Classifier

Objective task-size signal that feeds the `trivial | standard | complex` vocabulary
used by `/plan` (step 5a tier), `/build` (per-step review depth), and the
orchestrator's no-plan fast path. **Never re-classify using a fresh LLM judgement** —
derive the tier from the objective signals below.

Calibrated from `docs/experiments/data/3sizes-3arms-summary.json`.

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

## Classification Rules

Apply in order; the first match wins.

### Trivial (no-plan fast path eligible)

**ALL** of the following must hold:

- `files_changed` ≤ 1
- `loc_delta` ≤ 50
- `slice_count` ≤ 1
- `wave_count` ≤ 1
- `has_complex_step` = false
- `decision_axis_triggered` = false  ← AC5 guardrail: never skips plan for high-reversal-cost work

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
**Decision**: Classified as <trivial|standard|complex>
**Inputs**: files_changed=<N>, loc_delta=<N>, slice_count=<N>, wave_count=<N>, has_complex_step=<bool>, decision_axis_triggered=<bool>
**Rationale**: <which rule fired>
```
