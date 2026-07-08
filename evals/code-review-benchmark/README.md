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
against the actual datasets has not been run** — both dataset homes are
now auto-provisioned (#949) rather than requiring a pre-existing checkout,
but running that first live sweep in an environment with real network
access and reporting the real recall number back on #821 is still the
natural next step.

## Prerequisites

Both dataset homes are **auto-provisioned** (#949) into a gitignored,
repo-local `.cache/` on first use — no manual cloning required:

- **Defects4J**: cloned from <https://github.com/rjust/defects4j> into
  `.cache/defects4j`, then its `./init.sh` is run once (downloads the Major
  mutation tool + supporting libraries — slow and network-heavy; a
  `.cache/defects4j/.d4j-init-complete` marker file means later runs skip
  straight to using it). The resolved `framework/bin/defects4j` binary is
  used directly — it's never required on `PATH`.
- **BugsJS**: cloned from <https://github.com/BugsJS/bug-dataset> into
  `.cache/bugsjs-bug-dataset`.
- Pass `--defects4j-home`/`DEFECTS4J_HOME` or `--bugsjs-home`/`BUGSJS_HOME`
  to use an existing checkout instead (skips auto-provisioning entirely —
  an explicit-but-broken path still fails loudly rather than being
  silently overridden).

Auto-provisioning does **not** remove every system-level prerequisite:
Defects4J's `init.sh` still needs `wget`, Perl (+ its cpan modules), a
Java 11 JDK, `git`, and `svn` on the machine; `git` itself is needed for
both clones. Confirmed live on a real machine: `brew install wget
openjdk@11 cpanminus` + `cpanm --local-lib=~/perl5 --installdeps .` (run
inside `.cache/defects4j`) covers all of it on macOS.

Two of those (Java 11, the Perl CPAN modules) are resolved **inside the
harness itself** (#951), not via your shell profile — every `defects4j`
subprocess call gets a scoped `env` override, built by
`adapters/bootstrap.build_defects4j_env()`:

- **Java 11**: tries `/usr/libexec/java_home -v 11` (macOS), then `brew
  --prefix openjdk@11` (the common case for a keg-only Homebrew install).
- **Perl CPAN deps**: `~/perl5/lib/perl5` if present (the `cpanm
  --local-lib=~/perl5` convention above).

This never touches your actual `JAVA_HOME`/`PATH`/`PERL5LIB` or `~/.zshrc`
— only the subprocess environment `defects4j` itself runs under. If
neither resolves, `defects4j` calls fall back to your inherited
environment unchanged (today's behavior, and where you'd see the Perl/Java
errors this was built to avoid).

- The `claude` CLI available on `PATH` (used headlessly via
  `plugins/dev-team/skills/headless-run/scripts/isolated_dispatch.py`'s
  session-isolation approach — see #842), authenticated via `claude login`
  (a subscription). Each dispatch runs in a fresh, isolated `HOME` — but
  `~/.claude.json` alone isn't enough to keep that dispatch logged in
  (confirmed empirically), so `copy_auth_state()` (#957) also carries over
  most of `~/.claude/` itself (settings, `projects/`, `sessions/`,
  `mcpServers`, `plugins/`) so it doesn't need `ANTHROPIC_API_KEY`. The
  clearly bulky, clearly-not-auth-related pieces (`history.jsonl`,
  `file-history/`, `session-env/`, `paste-cache/`, `shell-snapshots/`,
  `debug/`, `telemetry/`, `downloads/`) are excluded — see
  `_CLAUDE_DIR_EXCLUDE` in `isolated_dispatch.py` — but this is still a
  real departure from the "clean isolated HOME" the underlying script was
  built for; there's no confirmed narrower answer for exactly which single
  piece under `~/.claude/` gates the login check.

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
`runner._extract_review_json()` extracts it. In practice the model often
narrates before the fence despite the contract (e.g. "Emitting the
required aggregated JSON per contract:\n\n```json\n{...}"), confirmed live
in a real sweep where this cost 40% recall (#963) — the extractor
searches for a fenced```json block anywhere in the text (last one first,
falling back to earlier ones) rather than requiring the whole response to
be just the fence. If the model's final text has no JSON at all (not just
a formatting quirk — the payload was never actually emitted in that
turn), the harness retries once via the same-session `--resume` backstop
(see "Narration instead of JSON" below, #999/#1002) before giving up; only
if that retry also fails does it show up as "unparseable --json output
(after retry)".

## Usage

```bash
# Smoke test: a handful of Lang bugs
python3 cli.py --dataset defects4j --project Lang --sample 5

# One BugsJS project, resumable across a long run
python3 cli.py --dataset bugsjs --project Bower --resume

# Everything Defects4J has, capped to the first 2 projects, full-repo scope
python3 cli.py --dataset defects4j --limit-projects 2 --full-repo

# Full sweep: every project in both datasets (same --results-dir, so
# results.jsonl accumulates across both runs and report.md covers both).
# --workers left at its default (2) here deliberately — see #974 below on
# why a higher value multiplies concurrent nested `claude -p` dispatches.
python3 cli.py --dataset defects4j
python3 cli.py --dataset bugsjs

# Regenerate report.md from existing results.jsonl without re-dispatching
python3 cli.py --report-only

# Deterministic verification sweep pinned to specific, known bug IDs —
# e.g. re-running the exact cases a prior sweep flagged, for a reproducible
# regression check (#970) instead of --sample's unseeded random selection
python3 cli.py --dataset defects4j --project Lang --bug-ids 36,44,7,23,56

# Cap real spend on a long unattended sweep — stops dispatching NEW cases
# once the running total meets/exceeds $50 (already in-flight cases still
# finish; nothing is silently dropped, see Cost tracking below)
python3 cli.py --dataset defects4j --max-cost-usd 50
```

### Flags

| Flag | Meaning |
| --- | --- |
| `--dataset {defects4j,bugsjs}` | Required (unless `--report-only`) |
| `--project <name>` | Filter to a single project |
| `--sample N` | Random sample of N bugs per project |
| `--bug-ids <id,id,...>` | Explicit, comma-separated bug IDs — deterministic, takes precedence over `--sample` |
| `--resume` | Skip cases already recorded in `results.jsonl`/`skipped.jsonl` |
| `--full-repo` | Review the whole checkout instead of just the fix's files (cost control is on by default: only ground-truth files are copied into scope) |
| `--limit-projects N` | Cap the number of projects processed |
| `--tolerance N` | Line-range tolerance for hit scoring (default 3) |
| `--model` | Model tier passed to the `/code-review` dispatch (default `sonnet`) |
| `--timeout` | Per-case dispatch timeout in seconds (default 1800 — raised from 900 after #974: a "single file" review still fans out to the full ~14-agent roster, not a lightweight pass; see `runner.make_isolated_dispatch_fn`'s docstring for the measured evidence) |
| `--workers` | Number of bug cases run concurrently, thread pool (default 2 — lowered from 4 after #974 to bound how many ~14-20-way agent fan-outs run concurrently on one host) |
| `--max-cost-usd N` | Fail-safe spend cutoff in USD (#1000, default: no cap) — see Cost tracking below |
| `--no-verify-tests` | Skip building/installing deps and running the project's own test suite per case (on by default; diagnostic only — see below) |
| `--no-json-retry` | Disable the #999/#1002 retry-once backstop for narration-instead-of-JSON dispatches (on by default — see "Narration instead of JSON" below) |
| `--json-retry-timeout N` | Subprocess timeout, seconds, for the retry-once follow-up specifically (default: unset, falls back to `min(--timeout, 300)` — deliberately smaller than `--timeout`, since the retry is meant to be a cheap same-session re-emission, not a fresh review) |
| `--defects4j-home`, `--bugsjs-home` | Dataset home dirs (or the matching env vars) |
| `--results-dir` | Where `results.jsonl`/`skipped.jsonl`/`report.md`/`raw/` are written (default `./results`) |
| `--report-only` | Only (re)generate `report.md` from existing results |

## Cost tracking (#1000)

Real per-case dispatch cost is real money — #974 measured $1.29 (a
deliberately trivial single file) to $4.48 (a real Defects4J case) per
`/code-review --json` dispatch. Three things make spend visible and
boundable instead of a surprise at the end of a long sweep:

- **A running total on every progress line**: `[3/10] defects4j:Lang:23:
  HIT ($6.12 total)` — sourced from `total_cost_usd` in the underlying
  `claude -p --output-format json` wrapper.
- **A pre-sweep estimate**, printed to stderr before any dispatch begins:
  `case_count * $4.50` (a conservative hardcoded constant, not
  extrapolated from live cases — see the plan's Decisions & Assumptions
  for why). Skipped when there's nothing to dispatch (`--report-only`, or
  a `--resume` run that already covers every case).
- **`--max-cost-usd <N>`**, a fail-safe cutoff, not an exact ceiling: it's
  checked only *after* a case completes — never before the initial
  `--workers`-sized batch is primed — so realized spend can exceed `N` by
  up to `workers - 1` extra in-flight cases' cost. Once the running total
  meets/exceeds `N`, no further case is submitted; cases already in flight
  are never cancelled and always finish normally. Cases that never got to
  start are recorded to `skipped.jsonl` with a reason naming
  `--max-cost-usd` (never silently dropped), and a stderr message
  explains the stop. `report.md`'s summary line also sums the total spent
  across `results.jsonl` + `skipped.jsonl` (a case skipped for
  "unparseable --json output" still paid for a real dispatch).

The scheduling itself lives in `scheduler.py`, not `cli.py` — see Layout
below.

## Output artifacts (`results/`, gitignored)

- `results.jsonl` — one record per attempted bug: `{dataset, project, bug_id,
  hit, ground_truth_hunks, findings, unmatched_findings, raw_output_path,
  test_verification, cost_usd}`.
- `skipped.jsonl` — one record per bug that couldn't be checked out or
  scored: `{dataset, project, bug_id, reason, cost_usd}`. `reason` is one
  of: `checkout failed`, `no ground-truth hunks`, `unparseable --json
  output` (or `unparseable --json output (after retry)` — see "Narration
  instead of JSON" below), `ground truth touches no recognized source
  files` (the fix's own commit bundled with its tests touched nothing but
  a changelog/manifest/CI-config file — e.g. `History.md`, `package.json`,
  `.travis.yml` — so there was no source change for `/code-review` to have
  found; scored as a skip, not a recall miss), or a message naming
  `--max-cost-usd` (#1000 — the sweep's budget was reached before this
  case could be dispatched).
- `cost_usd` (#1000, both files above) — the dispatch's `total_cost_usd`
  from the underlying `claude -p --output-format json` wrapper (summed
  across both attempts when the #999/#1002 retry-once backstop fired), or
  `None` when no dispatch happened (checkout failure, no ground truth,
  budget cut off before this case started) or the wrapper never reported
  one (e.g. a timeout).
- `raw/<dataset>-<project>-<bug_id>.txt` — the dispatch's raw stdout,
  verbatim, saved before any parsing (so a parser bug never loses data). If
  the #999/#1002 retry-once backstop fired, this file has BOTH attempts:
  the primary dispatch's raw stdout, then a `--- #999/#1002 JSON-retry
  follow-up (--resume) ---` delimiter, then the retry's raw stdout (or a
  placeholder noting the retry subprocess itself failed/timed out).
- `report.md` — overall/per-dataset/per-project recall, a **Missed Defects**
  section (the actionable part), a noise summary (average unmatched
  findings per hit run — "unmatched," not "false positive": the review may
  have found a real, different issue), and a total-cost line (#1000)
  summed across `results.jsonl` + `skipped.jsonl`.

### Narration instead of JSON (#967, #975, #999, #1002)

A completed, otherwise-successful `/code-review --json` dispatch
occasionally narrates having emitted its JSON payload instead of actually
emitting it (e.g. "Aggregated JSON emitted to stdout per `--json` contract;
run stops here" — no `{...}` object anywhere in the text). PR #975 hardened
the skill's step-7 wording specifically to forbid this, but #999 and #1002
each independently reproduced it again afterward, on cases at opposite ends
of the harness's turn-count range (58 turns and 15 turns) — evidence that a
wording-only fix doesn't reliably close the gap; see
`plans/issue-999-1002-json-narration.md` for the full investigation.

`make_isolated_dispatch_fn` (this is where `--no-json-retry` and
`--json-retry-timeout` apply) now retries exactly once when this happens:
it resumes the SAME session (`claude -p --resume <session_id>`, not a fresh
dispatch) with a short instruction to re-emit only the JSON, since the
review's findings are already in that session's context and don't need to
be redone. If the retry succeeds, the case scores normally. If it also
fails, the case is skipped with reason `unparseable --json output (after
retry)` so it's distinguishable in `skipped.jsonl`/`report.md` from a case
where no retry was ever attempted (e.g. the first dispatch itself errored
or timed out — retrying a broken run's session isn't expected to help).

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

Cases run concurrently across a thread pool (`--workers`, default 2 (#974))
— each case does its own checkout into a private temp dir and its own
subprocess calls (git/defects4j/npm/`claude`), so cases don't share mutable
state. Raise `--workers` for a faster full sweep; keep it low if you're
worried about hitting rate limits on the underlying `claude -p` dispatches:
each "case" is itself a ~14-20-way parallel agent fan-out (see
`runner.make_isolated_dispatch_fn`'s docstring), so `--workers 4` means up
to ~60-80 concurrent nested `claude -p` dispatches, not 4.

## Layout

```
adapters/
  common.py              # BenchmarkCase, unified_diff_hunks(), run_with_timeout
  bootstrap.py            # auto-clone/init both dataset homes into .cache/ (#949); resolves Java 11 + Perl CPAN env for defects4j subprocess calls (#951)
  defects4j_adapter.py    # active-bugs.csv + .src.patch -> BenchmarkCase; run_tests() = compile+test
  bugsjs_adapter.py       # Projects.csv + <Project>_bugs.csv + git tags -> BenchmarkCase; run_tests() = npm install+test
runner.py                 # checkout -> scope -> dispatch -> parse -> score -> JSONL
scorer.py                 # hit/miss/tolerance/unmatched-findings
report.py                 # results.jsonl + skipped.jsonl -> report.md
scheduler.py              # #1000: budget-aware, submit-as-you-go case scheduling (--max-cost-usd)
cli.py                    # argparse entry point
fixtures/                 # real (trimmed) sample data used by the unit tests
```
