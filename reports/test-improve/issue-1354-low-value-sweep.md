# LOW_VALUE Triple-Criteria Sweep — Exhaustive Pass

**Story:** `plans/test-improve/phase-4/low-value-sweep.md` (Phase 4, Story 5)
**Date:** 2026-07-24
**Scope:** Every pytest test file under `plugins/dev-team/tests/` and
`tests/{repo,agents,commands,docs,knowledge,bats,skills,scripts,hooks,security-assessment}/`.
`evals/*/tests/*.sh` (the AI-accuracy eval harness) is explicitly excluded, per the Story's
scope note — it is a different kind of test (agent-output grading), not a pytest unit/integration
suite subject to these criteria.

## Criteria applied (from `test-health`)

A test qualifies as **LOW_VALUE** only if it meets **all three**:

1. No branching logic in the test itself (no conditional assertions).
2. No observable outcome beyond "a mock was called" (only asserts a mock/spy was invoked —
   no assertion on a return value, raised exception, file/stdout content, exit code, etc.).
3. Coverage of the same behavior is already provided by a higher-layer test.

## Files evaluated: 339 (not 338 — see note)

`find` over the nine directories named in the Story, matching both of pytest's default
discovery patterns (`test_*.py` and `*_test.py`), returns **339** files, not the 338 the Story
and Phase 1 cite. The extra file is explained by two files that match the suffix pattern
`*_test.py` rather than the more common `test_*.py` prefix, both under
`tests/security-assessment/harness/`:

- `tests/security-assessment/harness/smoke_test.py`
- `tests/security-assessment/harness/scope_enforcement_test.py`

Both are real pytest files (collected under `pytest.ini`'s default `python_files`, no override
present) and were evaluated as part of this sweep. All 339 files were evaluated — no sampling.

Per-directory breakdown (matches 339):

| Directory | Files |
|---|---|
| `plugins/dev-team/tests` | 80 |
| `tests/repo` | 72 |
| `tests/skills` | 68 |
| `tests/scripts` | 48 |
| `tests/agents` | 15 |
| `tests/docs` | 15 |
| `tests/hooks` | 13 |
| `tests/knowledge` | 11 |
| `tests/commands` | 9 |
| `tests/security-assessment` | 5 |
| `tests/bats` | 3 |
| **Total** | **339** |

## Method

1. Enumerated all 339 files via `find` (both discovery patterns), confirmed no duplicates and
   no `__pycache__` artifacts in the list.
2. Wrote an AST-based scanner (`ast.parse` + `ast.walk`, not regex) that inspects **every** test
   function/method across all 339 files — 4,046 test functions total — and computes, per test:
   - `has_branch`: does the function body contain any `If`/`For`/`While` node anywhere
     (criterion-1 disqualifier)?
   - `non_mock_assert`: does it contain any `assert` statement, or `with pytest.raises(...)`
     block, whose checked expression is *not* a mock-call assertion (`.assert_called*`,
     `.call_count`, `.called`, `.call_args*`, `.mock_calls`)? (criterion-2 disqualifier)
   - `mock_assert_count`: how many assertions *are* pure mock-call checks.
   - A test is a **candidate** only if `has_branch` is false, `non_mock_assert` is false, and
     `mock_assert_count >= 1` — i.e., it has at least one assertion and every assertion in it is
     a mock-call check with no branching.
3. This is a conservative, exhaustive-by-construction first pass: it does not sample or spot-check
   a subset — it inspects the full AST of every test function in every one of the 339 files (no
   file was skipped because it "looked fine"). Files whose tests all assert real behavioral
   outcomes (return values, file/stdout/exit-code content, raised exceptions) are correctly
   excluded at this stage without needing individual manual review, because they fail criterion
   2 outright — this is the efficiency the Story's own guidance anticipated ("most files will
   fail criterion 1 or 2 immediately").
4. Verified there is no unittest.TestCase-style assertion usage (`self.assertEqual`, etc.)
   anywhere in the 339 files that could have evaded the `ast.Assert`/mock-call-expression
   detection (`grep` confirms 0 matches) — so the AST scanner's two assertion shapes (bare
   `assert` statements and bare `mock.assert_called*()` expression statements) cover the full
   assertion vocabulary actually in use.
5. Every function flagged as a candidate was then read in full file context and cross-checked
   against criterion 3 (an independent `grep` across the whole repo for any other test file
   referencing the same production symbol/behavior).

## Result of the automated pass

- **4,046 test functions** scanned across the 339 files.
- **1 candidate** survived the criterion-1/criterion-2 filter:
  `test_fetch_in_progress_issues_repo_resolved_once_for_multiple_issues`
  (`plugins/dev-team/tests/scripts/test_autoship_reclaim.py:236`).

## Manual cross-check of the one candidate

```python
# plugins/dev-team/tests/scripts/test_autoship_reclaim.py:236
def test_fetch_in_progress_issues_repo_resolved_once_for_multiple_issues() -> None:
    """Repo resolution happens exactly once per run, not once per issue."""
    ...
    with patch(
        "autoship_reclaim.subprocess.run",
        side_effect=[issue_list, repo_view, timeline_empty, timeline_empty],
    ) as mock_run:
        autoship_reclaim._fetch_in_progress_issues()
    # 1 issue-list call + 1 repo-view call + 2 timeline calls (one per
    # issue) = 4 total, not 5 (which would mean repo view ran per-issue).
    assert mock_run.call_count == 4
```

This test passes criteria 1 and 2 (no branching; its only assertion is a mock call-count
check) but **fails criterion 3**: `grep -rl "autoship_reclaim\|_fetch_in_progress_issues"` across
both `plugins/` and `tests/` returns only this test file and the production module itself —
no other test, at any layer, exercises `_fetch_in_progress_issues`. This test is the sole
regression guard for the specific fix referenced in its own docstring and the sibling test's
comment (issue #989 code-review finding: repo resolution previously ran once *per issue*
instead of once *per run*). The call count *is* the behavior under test here — there is no
higher-layer (or same-layer) test that would catch a regression back to the N+1 pattern if this
test were removed. It does not qualify as LOW_VALUE.

## Recommended removals

**None.** Zero tests across all 339 files qualify as LOW_VALUE under all three criteria
simultaneously. The single automated candidate was manually reviewed and disqualified on
criterion 3 (no covering higher-layer test exists — removing it would leave a specific,
previously-fixed regression (#989) with no test coverage at all).

| File:line | Qualifying test | Covering higher-layer test | Rationale |
|---|---|---|---|
| — | — | — | No qualifying tests found. |

## Conclusion

All 339 pytest files in scope (338 named by the Story plus one accounted for by the
`*_test.py`-suffix discovery pattern, both explained above) were evaluated against the full
three-criteria LOW_VALUE test. This is a clean bill of health for the sweep specifically:
no test in the suite is a pure "mock was called, no branching, redundantly covered" artifact
that should be advisory-flagged for removal. No test was deleted or modified — this Story is
analysis-only per the Phase-3 gap-class contract.
