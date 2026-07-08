---
name: co-evolution-audit
description: >-
  Flag production files that churn repeatedly while their paired test files do
  not change — the "Red Queen" co-evolution gap. Uses git log --stat to compute
  per-file change frequency over a configurable window, applies language-aware
  pairing heuristics (Python, JS/TS, Go, Java, C#), and produces a ranked table
  of stale-coverage pairs. Feeds test-health and test-improve as prioritization
  input, not a standalone gate. Use when you want to find high-churn files whose
  tests have gone stale, or before running /test-improve to identify the highest-
  leverage targets first.
argument-hint: "[--since <date|N-days>] [--max-commits <N>] [--min-churn <N>] [--max-test-churn <N>]"
user-invocable: true
effort: low
---

# Co-Evolution Audit

Role: worker. Reads git history, pairs production files to their test files,
and reports stale-coverage pairs. Does not edit any code or tests.

## The Problem

A file that churns repeatedly while its tests never change is a high-risk
signal: the tests are likely passing for structural reasons (they still
compile and run) rather than because they verify current behavior. This
divergence is invisible to coverage tools — coverage stays green even as
the behavioral gap widens with every production change.

## Parse Arguments

Arguments: $ARGUMENTS

| Flag | Default | Meaning |
|---|---|---|
| `--since <date\|N-days>` | `90 days ago` | Lookback window. Accepts ISO date (`2025-01-01`) or relative (`90 days ago`). |
| `--max-commits <N>` | `200` | Cap on commits scanned. The window is the earlier of `--since` and `--max-commits`. |
| `--min-churn <N>` | `3` | Minimum production-file change count to flag a pair. |
| `--max-test-churn <N>` | `1` | Maximum test-file change count for a pair to be flagged. A pair is flagged when production churn ≥ `--min-churn` AND test churn ≤ `--max-test-churn`. |

## Graceful skip conditions

If any of the following is true, print a one-line notice and exit cleanly
(do not fail):

- The working directory has no `.git` directory and is not inside a git
  repository (`git rev-parse --git-dir` fails).
- `git log` returns zero commits in the requested window.
- The repository is a shallow clone with fewer than 10 commits.

## Step 1: Collect churn data

Run git log to collect per-file change frequency over the window:

```bash
git log --since="90 days ago" --max-count=200 --name-only \
    --pretty=format:"" -- . | grep -v '^$' | sort | uniq -c | sort -rn
```

This produces a frequency table: how many commits touched each file.

Alternatively, `--stat` can be used for a combined view:

```bash
git log --since="90 days ago" --max-count=200 --stat \
    --pretty=format:"COMMIT:%H"
```

Parse the output into a map: `file_path → commit_count`. Exclude merge
commits (`--no-merges`) to avoid inflating counts from merge-heavy workflows.

Practical command:

```bash
git log --since="90 days ago" --max-count=200 --no-merges \
    --name-only --pretty=format:"" | grep -v '^$' | sort | uniq -c
```

## Step 2: Classify files

Partition the file map into two groups:

1. **Production files** — any file that is not in a test bucket (see Step 3
   for the test-file heuristics). When in doubt, prefer to classify a file
   as production rather than drop it.
2. **Test files** — files matched by the pairing heuristics below.

## Step 3: Pair production files to test files

Apply pairing heuristics in priority order. The first matching rule wins.

### Python

| Production file | Candidate test files (checked in order) |
|---|---|
| `src/foo.py` | `tests/test_foo.py`, `tests/foo_test.py`, `test_foo.py` |
| `pkg/bar/baz.py` | `pkg/bar/tests/test_baz.py`, `tests/test_baz.py`, `test_baz.py` |

Rule: strip leading path prefix (`src/`, package dirs) and try:
`tests/test_<stem>.py` → `<dir>/tests/test_<stem>.py` → `test_<stem>.py`.

Test-file markers: path contains `test` or `spec`; filename starts with
`test_` or ends with `_test.py`.

### JavaScript / TypeScript

| Production file | Candidate test files (checked in order) |
|---|---|
| `src/foo.ts` | `src/foo.test.ts`, `src/__tests__/foo.test.ts`, `src/foo.spec.ts` |
| `lib/bar.js` | `lib/bar.test.js`, `lib/__tests__/bar.test.js`, `lib/bar.spec.js` |

Rule: same directory, add `.test.<ext>` or `.spec.<ext>` suffix; OR look
for a `__tests__/` sibling directory with the same base name.

Test-file markers: filename ends with `.test.ts`, `.test.js`, `.spec.ts`,
`.spec.js`; path contains `__tests__` or `__spec__`.

### Go

| Production file | Candidate test files (checked in order) |
|---|---|
| `pkg/foo/bar.go` | `pkg/foo/bar_test.go` |
| `cmd/app/main.go` | `cmd/app/main_test.go` |

Rule: Go's convention is strict — test file is always `<stem>_test.go` in
the same directory. No other candidate is checked.

Test-file markers: filename ends with `_test.go`.

### Java

| Production file | Candidate test files (checked in order) |
|---|---|
| `src/main/java/com/example/Foo.java` | `src/test/java/com/example/FooTest.java`, `src/test/java/com/example/FooSpec.java` |

Rule: swap `src/main/java` → `src/test/java`, append `Test` or `Spec` to
the class name.

Test-file markers: path contains `src/test`; class name ends with `Test`
or `Spec`.

### C# / .NET

| Production file | Candidate test files (checked in order) |
|---|---|
| `src/Foo/Bar.cs` | `tests/Foo.Tests/BarTests.cs`, `tests/Foo.Tests/BarTest.cs` |
| `src/Project/Service.cs` | `tests/Project.Tests/ServiceTests.cs` |

Rule: look for a sibling `*.Tests` or `*.Test` project directory; append
`Tests` or `Test` to the class stem.

Test-file markers: path contains `.Tests/` or `.Test/`; class name ends
with `Tests` or `Test`.

### Fallback (unknown language)

If no language-specific rule matches, apply the generic heuristic:
look for a file whose path contains `test` or `spec` and whose stem
contains the production file's stem (case-insensitive).

### No test file found

If no candidate test file exists in the git history (it was never
committed), record `test_churn = 0` and `test_file = "(none found)"`.
These pairs have the highest co-evolution gap and should rank first.

## Step 4: Compute co-evolution gap

For each production file with `prod_churn >= --min-churn`:

1. Find its paired test file via Step 3.
2. Look up `test_churn` from the churn map (0 if no test file exists or
   the test file had zero commits in the window).
3. Flag the pair if `test_churn <= --max-test-churn`.

**Gap score** (for ranking): `prod_churn - test_churn`. Higher score =
wider divergence.

## Step 5: Report

### Summary line

```
Co-Evolution Audit  window: 90 days / 200 commits  flagged: N of M pairs
```

### Flagged pairs table

Sort by gap score descending (widest divergence first).

```
| Rank | Production file           | Prod churn | Test file                      | Test churn | Gap |
|------|---------------------------|-----------|--------------------------------|-----------|-----|
|    1 | src/auth/session.py       |        18 | tests/test_session.py          |         0 |  18 |
|    2 | src/billing/invoice.py    |        12 | tests/test_invoice.py          |         1 |  11 |
|    3 | src/api/routes.ts         |         9 | src/api/routes.test.ts         |         0 |   9 |
|    4 | src/cache/store.go        |         7 | (none found)                   |         0 |   7 |
```

### Clean pairs (informational, collapsed)

Files that passed the churn threshold but whose tests co-evolved (test
churn > `--max-test-churn`) are listed in a collapsed section as evidence
that the pairing heuristic is working, not a concern.

### No findings

If no pairs are flagged, print:

```
No co-evolution gaps found in the audit window. All high-churn production
files have co-evolving test files, or no file exceeded --min-churn (3).
```

## Step 6: Remediation guidance

After the table, print a prioritized action list:

### Immediate priorities (gap ≥ 5 or test_file = "none found")

These are the highest-risk files: they changed frequently but tests did
not follow. Recommended next steps:

1. **Run `/test-improve` on the flagged file** — the test-improve skill
   will assess the existing tests for the file and propose targeted
   improvements. Pass the flagged production file path as the scope.

   Example: `/test-improve --scope src/auth/session.py`

2. **Run `/mutation-testing` on the flagged file** — stale tests often
   have missing assertions that mutation testing will surface. Run after
   `/test-improve` has added structural coverage.

   Example: `/mutation-testing --scope src/auth/session.py`

3. **Check for a missing test file** — if `test_file = "(none found)"`,
   the production file has never had a dedicated test file. Creating one
   is higher leverage than improving an existing sparse test file.

### Secondary priorities (gap 2–4)

These pairs have some test co-evolution but lag behind production churn.
Feed them to `/test-health` as context: these files are candidates for
the suite's coverage improvement roadmap, but they are not urgent fire
drills.

### Integration with other skills

| Signal | Where to send it |
|---|---|
| `gap ≥ 5` or `test_file = "(none found)"` | `/test-improve` (immediate) |
| `gap 2–4` | `/test-health` (roadmap input) |
| Any flagged file | `/mutation-testing` (after coverage is added) |
| Flagged file also has review findings | Treat as compounding risk — prioritize above clean flagged files |

## Constraints

- **Advisory only.** Do not edit any files.
- **No git rewrite.** Never run any git command that modifies history
  (`reset`, `rebase`, `cherry-pick`, `push`). Read-only git commands only.
- **Graceful skip over binary and generated files.** Skip files matching
  common generated-file patterns (`*.pb.go`, `*.generated.cs`,
  `migrations/*.sql`, `dist/*`, `vendor/*`, `node_modules/*`). These are
  not hand-authored code and their churn inflates the signal.
- **Shallow clones.** If the repo is shallow (fewer than 10 commits
  visible), note it in the summary and advise the operator to run on a
  full clone for a meaningful signal.
- **Not a gate.** Co-evolution audit is a prioritization input, not a
  pass/fail quality gate. Do not block CI or a PR on its output.
