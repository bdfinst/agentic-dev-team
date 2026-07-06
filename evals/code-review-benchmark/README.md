# /code-review Benchmark Harness (#821)

Checks out real, known-defect commits from Defects4J (Java) and BugsJS
(JavaScript), runs `/code-review` against the buggy revision, and scores
whether the review's findings actually cover the real defect location.

Built after #885 (a `correctness-review` agent) closed the recall gap that
had blocked this harness: the #852 stress test found the roster scored 0/4
on functional-correctness bugs (missing assignments, non-interpolated
literals, missing guards, boundary omissions) — exactly the defect class
Defects4J/BugsJS inject.

## Status

The harness (adapters, runner, scorer, report generator) is implemented and
unit-tested against **real** fixture data (a real Defects4J patch, a real
`active-bugs.csv`, a real BugsJS `Projects.csv`/`<Project>_bugs.csv`) — see
`tests/scripts/test_code_review_benchmark_*.py`. **A live end-to-end sweep
against the actual datasets has not been run** — neither `defects4j` nor a
`BugsJS/bug-dataset` checkout exists in this repo's dev environment.
Running one and reporting the real recall number back on #821 is the
natural next step.

## Prerequisites

- **Defects4J**: `defects4j` on `PATH`, and `DEFECTS4J_HOME` (or
  `--defects4j-home`) pointing at a full framework checkout (has
  `framework/projects/<Project>/active-bugs.csv` and
  `framework/projects/<Project>/patches/<bug_id>.src.patch` per project).
  See <https://github.com/rjust/defects4j>.
- **BugsJS**: `BUGSJS_HOME` (or `--bugsjs-home`) pointing at a local clone of
  <https://github.com/BugsJS/bug-dataset> (has `main.py`, `Projects.csv`, and
  `Projects/<Project>/<Project>_bugs.csv` per project).
- The `claude` CLI available on `PATH` (used headlessly via
  `plugins/dev-team/skills/headless-run/scripts/isolated_dispatch.py`'s
  session-isolation approach — see #842).

## Invocation contract (confirmed against the real skill, not assumed)

`/code-review --path <dir> --json` prints one aggregated JSON object to
stdout and nothing else:

```json
{
  "overall": "pass|warn|fail",
  "agents": [
    {
      "agentName": "correctness-review",
      "status": "warn",
      "issues": [
        {"severity": "error", "confidence": "high", "file": "...", "line": 42, "message": "..."}
      ],
      "summary": "..."
    }
  ],
  "totals": {"errors": 0, "warnings": 1, "suggestions": 0},
  "topFindings": ["..."],
  "summary": "..."
}
```

`--json` is contractually non-interactive and never writes files (see
`plugins/dev-team/skills/code-review/SKILL.md` / `output-format.md`). When
run headlessly via `claude -p ... --output-format json`, this payload is
the model's final text, nested in the wrapper JSON's `result` field —
`runner.make_isolated_dispatch_fn()` extracts it (stripping a markdown code
fence if the model added one).

## Usage

```bash
# Smoke test: a handful of Lang bugs
python3 cli.py --dataset defects4j --project Lang --sample 5

# One BugsJS project, resumable across a long run
python3 cli.py --dataset bugsjs --project Bower --resume

# Everything Defects4J has, capped to the first 2 projects, full-repo scope
python3 cli.py --dataset defects4j --limit-projects 2 --full-repo

# Full sweep: every project in both datasets (same --results-dir, so
# results.jsonl accumulates across both runs and report.md covers both)
python3 cli.py --dataset defects4j --workers 4
python3 cli.py --dataset bugsjs --workers 4

# Regenerate report.md from existing results.jsonl without re-dispatching
python3 cli.py --report-only
```

### Flags

| Flag | Meaning |
| --- | --- |
| `--dataset {defects4j,bugsjs}` | Required (unless `--report-only`) |
| `--project <name>` | Filter to a single project |
| `--sample N` | Random sample of N bugs per project |
| `--resume` | Skip cases already recorded in `results.jsonl`/`skipped.jsonl` |
| `--full-repo` | Review the whole checkout instead of just the fix's files (cost control is on by default: only ground-truth files are copied into scope) |
| `--limit-projects N` | Cap the number of projects processed |
| `--tolerance N` | Line-range tolerance for hit scoring (default 3) |
| `--model` | Model tier passed to the `/code-review` dispatch (default `sonnet`) |
| `--timeout` | Per-case dispatch timeout in seconds (default 900) |
| `--workers` | Number of bug cases run concurrently, thread pool (default 4) |
| `--no-verify-tests` | Skip building/installing deps and running the project's own test suite per case (on by default; diagnostic only — see below) |
| `--defects4j-home`, `--bugsjs-home` | Dataset home dirs (or the matching env vars) |
| `--results-dir` | Where `results.jsonl`/`skipped.jsonl`/`report.md`/`raw/` are written (default `./results`) |
| `--report-only` | Only (re)generate `report.md` from existing results |

## Output artifacts (`results/`, gitignored)

- `results.jsonl` — one record per attempted bug: `{dataset, project, bug_id,
  hit, ground_truth_hunks, findings, unmatched_findings, raw_output_path,
  test_verification}`.
- `skipped.jsonl` — one record per bug that couldn't be checked out or
  scored: `{dataset, project, bug_id, reason}`.
- `raw/<dataset>-<project>-<bug_id>.txt` — the dispatch's raw stdout,
  verbatim, saved before any parsing (so a parser bug never loses data).
- `report.md` — overall/per-dataset/per-project recall, a **Missed Defects**
  section (the actionable part), and a noise summary (average unmatched
  findings per hit run — "unmatched," not "false positive": the review may
  have found a real, different issue).

## Test verification (diagnostic, not a gate)

By default, before dispatching `/code-review`, each case configures and runs
the checked-out project's own test suite against the full checkout (not the
`fix-only` scoped copy, which won't have build files):

- **Defects4J**: `defects4j compile` then `defects4j test`, reading
  `<checkout>/failing_tests` for the reproduced trigger test(s).
- **BugsJS**: `npm ci` (if `package-lock.json` exists) or `npm install`,
  then `npm test`; a non-zero exit is the expected "bug reproduces" signal.

The result lands on the record as `test_verification: {configured, ran,
reproduced, ...}` (`None` when disabled). It is **never** used to skip or
exclude a case from scoring — Defects4J/BugsJS checkouts can fail to build
for reasons unrelated to the actual bug (JDK mismatch, npm registry
hiccup), and the harness's actual purpose (`/code-review` recall) must not
be silently distorted by environment noise. Disable it with
`--no-verify-tests` for a faster, cheaper smoke run. `report.md` summarizes
reproduced-vs-not when any case ran verification.

## Parallel execution

Cases run concurrently across a thread pool (`--workers`, default 4) — each
case does its own checkout into a private temp dir and its own subprocess
calls (git/defects4j/npm/`claude`), so cases don't share mutable state.
Raise `--workers` for a faster full sweep; keep it low if you're worried
about hitting rate limits on the underlying `claude -p` dispatches.

## Layout

```
adapters/
  common.py              # BenchmarkCase, unified_diff_hunks(), run_with_timeout
  defects4j_adapter.py    # active-bugs.csv + .src.patch -> BenchmarkCase; run_tests() = compile+test
  bugsjs_adapter.py       # Projects.csv + <Project>_bugs.csv + git tags -> BenchmarkCase; run_tests() = npm install+test
runner.py                 # checkout -> scope -> dispatch -> parse -> score -> JSONL
scorer.py                 # hit/miss/tolerance/unmatched-findings
report.py                 # results.jsonl + skipped.jsonl -> report.md
cli.py                    # argparse entry point
fixtures/                 # real (trimmed) sample data used by the unit tests
```
