# Complexity Regression Check — AC2 of Epic #362

**Issue:** #366 (P1-S2)
**Epic:** #362 (P1: Make review actually improve the code)
**Satisfies:** AC2 — mean `complexity-review` findings/solution drops below the pre-P1-S1 baseline (~5.3) on the 6 Campaign B tasks run test-first.

**Update (#2093):** `complexity-review` was folded into `structure-review` and
retired — its nesting-depth, cognitive-load, and async-pattern judgment now
live in `structure-review`'s charter. The history below is unchanged (it
describes what was true when this baseline was measured); the eval fixtures
(`cx-refactor-before`/`cx-refactor-after`) and the regression check now
target `structure-review`.

## Background

P1-S1 (PR #378) wired the REFACTOR step in the TDD skill to dispatch
`refactor-opportunity-review` and `complexity-review` after GREEN, with a bounded
fix loop that keeps tests green. Before that change, the RED-GREEN-REFACTOR cycle
stopped at GREEN — the dedicated REFACTOR agents were defined but never invoked.

This document establishes the before/after finding counts and the regression check
methodology.

## Baseline (before P1-S1)

Offline measurement: `complexity-review` run on the test-first solutions from
Campaign B (6 tasks, `sonnet-4-6`, 1 trial), before the REFACTOR loop was wired.

| Task | Findings (before) | Primary violations |
|------|--------------------|-------------------|
| stats | 2 | median() branch depth, sort usage |
| intervals | 4 | merge loop nesting, boundary conditions |
| timeparse | 5 | parse_duration character loop, cyclomatic complexity |
| money | 7 | format_money nesting, parse_money branch count |
| matrix | 3 | transpose nested loop, identity loop |
| csvlite | 11 | parse() monolith: line count, nesting depth, cyclomatic complexity |
| **Mean** | **5.3** | |

Data in: `docs/experiments/agentic-workflow-evidence/data/3sizes-3arms-summary.json` → `complexity_baseline`.

## Representative example: csvlite (before → after)

The csvlite task has the highest finding count (11) and best illustrates the
pattern: test-first under RED-GREEN stops as soon as tests pass, without
extracting helpers or reducing the state-machine's nesting.

### Before (typical test-first solution, pre-REFACTOR review)

See `evals/fixtures/cx-refactor-before/csvlite.py`. The `parse()` function:
- 50+ lines (threshold: <20)
- Cyclomatic complexity ~12 (threshold: <10) — separate if/elif chains for in-quotes
  vs. out-of-quotes, each with 4-5 branches
- Nesting depth 4 (`while → if in_quotes → if c == '"' → if lookahead`)

`complexity-review` output (representative):
```json
{
  "status": "fail",
  "issues": [
    {"severity": "error", "confidence": "high", "file": "csvlite.py", "line": 10,
     "message": "parse() is 51 lines (threshold: 20). Extract quoted-field handling into a helper."},
    {"severity": "error", "confidence": "high", "file": "csvlite.py", "line": 10,
     "message": "Cyclomatic complexity ~12 in parse() (threshold: 10). Flatten the in_quotes branch."},
    {"severity": "error", "confidence": "high", "file": "csvlite.py", "line": 14,
     "message": "Nesting depth 4 in parse() (threshold: 4). Extract _consume_quoted_field()."}
  ],
  "summary": "parse() is a monolith. Extract the quoted-field consumer into its own function."
}
```

Eval fixture: `evals/expected/cx-refactor-before.json` (expected: `fail`, ≥1 error).

### After (post-REFACTOR review, P1-S1)

See `evals/fixtures/cx-refactor-after/csvlite.py`. The REFACTOR loop:
1. `complexity-review` flagged `parse()` (line count + depth).
2. `refactor-opportunity-review` suggested extracting `_consume_quoted_field()`.
3. Auto-fix extracted the helper; tests re-ran green.

Result: `parse()` reduced to 16 lines; nesting depth 2; complexity 4.
`complexity-review` output (representative):
```json
{"status": "pass", "issues": [], "summary": "All functions within thresholds."}
```

Eval fixture: `evals/expected/cx-refactor-after.json` (expected: `pass`, 0 errors).

## Before / after summary

| State | Mean findings/solution | csvlite findings |
|-------|------------------------|-----------------|
| Before P1-S1 (no REFACTOR review) | **5.3** | 11 |
| After P1-S1 (REFACTOR dispatches review) | **target: < 5.3** | 0 (post-fix) |

The "after" mean is measured by `scripts/complexity-regression-check.sh` (see
below). AC2 passes when the measured mean is below 5.3.

## Regression check procedure

```bash
# Full regression (all 6 tasks, ~15-30 min, ~$2):
bash scripts/complexity-regression-check.sh

# With a specific model:
bash scripts/complexity-regression-check.sh --model claude-sonnet-4-6

# Eval fixtures only (instant, no model dispatch):
python3 scripts/eval_grade.py evals/expected/cx-refactor-before.json
python3 scripts/eval_grade.py evals/expected/cx-refactor-after.json
```

The eval fixtures (`cx-refactor-before`, `cx-refactor-after`) run as part of
`/agent-eval` and CI, so complexity regression is caught on every change to the
TDD skill's REFACTOR section or the complexity-review agent.

## What the regression catches

The eval pair acts as a unit test for the REFACTOR review loop:

- `cx-refactor-before` must return `fail` — if it passes, the fixture is too simple
  to distinguish pre- vs. post-REFACTOR code (the fixture itself degrades).
- `cx-refactor-after` must return `pass` — if it fails, the REFACTOR loop's
  auto-fix capability has regressed.

A CI failure on either fixture surfaces immediately, before any model dispatch.

## Limitations

1. **Single task sample.** The before/after eval pair uses csvlite (highest complexity).
   The full regression check runs all 6 tasks but requires model dispatch (~$2/run).

2. **One trial.** `complexity-review` findings vary slightly between runs (see P1-S3/S4
   for determinism hardening). The mean across 6 tasks is more stable than any single
   finding count.

3. **No change-stage measurement.** The regression check measures the build stage only
   (the state after REFACTOR review). Change-stage complexity is excluded (known
   harness artifact from Campaign B — see consolidated report).
