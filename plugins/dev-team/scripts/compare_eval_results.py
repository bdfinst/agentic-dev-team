#!/usr/bin/env python3
"""Diff two `/agent-eval` actuals result files and gate on detection
regression (#2169 Step 2.3).

`test-review.md`'s Phase 0 mechanical pre-phase (Step 2.3) must not decrease
detection quality relative to the current agent. This script makes that check
a re-runnable, checked-in gate instead of an eyeballed one-off comparison, so
future `test-review.md` edits can re-run the exact same regression check.

Inputs
------
`before`/`after` -- two `--actuals` JSON files in `eval_grade.py`'s own
documented shape (see that script's module docstring and
`skills/agent-eval/SKILL.md` Step 3 "Parse the agent's JSON output"):

    {
      "<fixture-stem>": {
        "agents": {
          "<agent-name>": {"status": "...", "issues": [...], "summary": "..."}
        }
      }
    }

`--expected-dir` (default `evals/expected`, mirroring `eval_grade.py`'s own
default) -- the eval corpus's expected/*.json files. Neither `eval_grade.py`
nor `/agent-eval`'s transcript schema carries an explicit true-positive/
false-positive count field anywhere -- the corpus's only ground truth is each
fixture/agent block's `issueCount` range (`evals/expected/*.json`). This
script uses that as the classification: a fixture/agent block whose
`issueCount.min > 0` is a **defect fixture** (built to contain a real,
detectable issue) -- the number of issues an agent reports against it is
read as a true-positive-count proxy. A block whose `issueCount.min == 0` is a
**clean fixture** (built to contain nothing worth flagging) -- the number of
issues reported against it is read as a false-positive-count proxy. This is
a fixture-level proxy, not a per-issue correctness judgment: it assumes every
issue reported on a defect fixture is (part of) the injected defect it was
built to catch, and every issue reported on a clean fixture is, by
construction, spurious. Reported/printed labels say so explicitly
(`TP-proxy`/`FP-proxy`); the JSON row shape avoids the vocabulary entirely
(`issuesBefore`/`issuesAfter`), letting `kind` carry the defect/clean
interpretation instead of implying a per-issue judgment this script does not
make.

Regression rule
----------------
Three cases, by whether an `(fixture, agent)` pair's issue count is present
in `before`/`after`:

- **Both present** -- for a defect fixture, `after` < `before` is a
  true-positive-count regression; for a clean fixture, `after` > `before` is
  a false-positive-count regression.
- **Present in `before`, absent from `after`** -- the agent produced no
  recorded result at all in the `after` run (errored, timed out, or was
  never dispatched for that pair). This is always scored as a regression --
  total detection loss is the worst-case outcome this gate exists to catch,
  regardless of whether the pair is a defect or clean fixture.
- **Absent from `before`** -- genuinely new coverage (or a pair neither run
  exercised); not comparable, skipped.

A fixture/agent block with no `issueCount` key, or a non-dict `issueCount`
value, is an explicit third "unclassified" state: counted separately in the
CLI's scope summary, never folded into "clean" -- an absent range is not
evidence a fixture is defect-free (`eval_graders/verdict.py`'s
`grade_verdict` already treats `issueCount` as optional and simply skips the
check when the key is absent; this script's classification must not
silently disagree with that by defaulting to "clean"). A malformed
(non-dict) `issueCount` value is treated the same way rather than raising --
a deliberate choice: a corpus authoring mistake should surface as "not
scored, look at this fixture", not crash the gate.

Relationship to `eval_grade.py --baseline`
--------------------------------------------
`eval_grade.py --baseline`/`--write-baseline` already tracks pass/fail
regression against a recorded grading baseline. This script is a narrower,
independent check: a raw issue-count delta between two actuals files, scoped
to true/false-positive-proxy counts only. It deliberately does not consult a
fixture's declared `issueCount.max` tolerance -- a fixture declaring
`{min: 0, max: 2}` still red-lines here on any 0-to-1 move, even though that
move is within the corpus's own declared tolerance. This is a scope choice,
not an oversight: this gate exists to catch any run-over-run regression in
detection count, not to re-enforce the corpus's own declared tolerance
ranges (that remains `eval_grade.py`'s job).

Shipped-tree placement
------------------------
This script lives in `plugins/dev-team/scripts/` (shipped) even though its
whole domain is the repo's own non-shipped `evals/` corpus. It mirrors the
existing precedent of `eval_ablation.py` (same directory, same repo-root
default) rather than introducing a new violation. It is monorepo-dev-only
tooling: useful only to a `test-review.md`/eval-corpus maintainer re-running
this exact regression check against this repo's own eval corpus, never
invoked by a downstream project that installs the plugin.

Exit codes
----------
0  every comparable fixture/agent pair is non-regressed
1  at least one fixture/agent pair regressed (readable diff on stdout)
2  usage / file-read / corpus error

Stdlib-only (ADR 0014/0015). See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KIND_DEFECT = "defect"
KIND_CLEAN = "clean"
KIND_UNCLASSIFIED = "unclassified"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_expected(expected_dir: Path) -> dict[str, dict]:
    """`{stem: {agent: expected_spec, ...}, ...}` for every `expected/*.json`
    under `expected_dir` that declares an `agents` block. Malformed expected
    files are skipped rather than raising -- this script's job is to compare
    result files, not to re-run `eval_grade.py --check-corpus`."""
    expected_by_stem: dict[str, dict] = {}
    for f in sorted(expected_dir.glob("*.json")):
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        agents = spec.get("agents")
        if isinstance(agents, dict) and agents:
            expected_by_stem[f.stem] = agents
    return expected_by_stem


def _issue_count(actuals: dict, stem: str, agent: str) -> int | None:
    """`len(issues)` for `stem`/`agent` in an actuals-shaped dict, or `None`
    when the pair has no recorded result (not comparable)."""
    entry = actuals.get(stem, {}).get("agents", {}).get(agent)
    if not isinstance(entry, dict):
        return None
    issues = entry.get("issues")
    if not isinstance(issues, list):
        return None
    return len(issues)


def _classify_kind(expected_spec: dict) -> str:
    """`KIND_DEFECT`/`KIND_CLEAN` from `issueCount.min`, or
    `KIND_UNCLASSIFIED` when `issueCount` is absent or not a dict (see the
    module docstring's "Regression rule" section for why this is a distinct
    third state rather than defaulting to "clean")."""
    issue_count_range = expected_spec.get("issueCount")
    if not isinstance(issue_count_range, dict):
        return KIND_UNCLASSIFIED
    return KIND_DEFECT if issue_count_range.get("min", 0) > 0 else KIND_CLEAN


def compute_fixture_diffs(before: dict, after: dict, expected: dict) -> tuple[list[dict], dict]:
    """`(rows, scope)` for every `(fixture stem, agent)` pair declared in
    `expected`.

    Each row is `{"fixture", "agent", "kind": "defect"|"clean",
    "issuesBefore", "issuesAfter", "regressed", "detail"}`. `issuesAfter` and
    `detail` are `None` except in the before-present/after-missing case (see
    the module docstring), where `issuesAfter` is `None` and `detail`
    explains why.

    A pair is left out of `rows` (and out of the regression count) when:
    - its expected block is malformed or its `issueCount` is absent/not a
      dict (`kind` would be `KIND_UNCLASSIFIED`) -- counted in
      `scope["skippedUnclassified"]`.
    - it has no recorded issue count in `before` at all -- counted in
      `scope["skippedNotComparable"]`.

    `scope` is `{"compared": int, "skippedNotComparable": int,
    "skippedUnclassified": int}` -- see finding #6 (scope truncation must be
    visible in output, not silently absorbed into "No regressions.")."""
    rows: list[dict] = []
    compared = 0
    skipped_not_comparable = 0
    skipped_unclassified = 0

    for stem, agents in expected.items():
        for agent, expected_spec in agents.items():
            if not isinstance(expected_spec, dict):
                skipped_unclassified += 1
                continue

            kind = _classify_kind(expected_spec)
            if kind == KIND_UNCLASSIFIED:
                skipped_unclassified += 1
                continue

            before_n = _issue_count(before, stem, agent)
            if before_n is None:
                skipped_not_comparable += 1  # absent from `before` -- new coverage, not comparable
                continue

            after_n = _issue_count(after, stem, agent)
            detail = None
            if after_n is None:
                # Present in `before`, absent from `after`: total detection
                # loss -- always a regression, regardless of kind.
                regressed = True
                detail = "no result recorded in after"
            elif kind == KIND_DEFECT:
                regressed = after_n < before_n
            else:
                regressed = after_n > before_n

            rows.append(
                {
                    "fixture": stem,
                    "agent": agent,
                    "kind": kind,
                    "issuesBefore": before_n,
                    "issuesAfter": after_n,
                    "regressed": regressed,
                    "detail": detail,
                }
            )
            compared += 1

    rows.sort(key=lambda r: (r["fixture"], r["agent"]))
    scope = {
        "compared": compared,
        "skippedNotComparable": skipped_not_comparable,
        "skippedUnclassified": skipped_unclassified,
    }
    return rows, scope


def _format_row(row: dict) -> str:
    pair = f"{row['fixture']}::{row['agent']}"
    label = "TP-proxy" if row["kind"] == KIND_DEFECT else "FP-proxy"
    after_display = row["issuesAfter"] if row["issuesAfter"] is not None else "MISSING"
    detail = f"{label}: {row['issuesBefore']} -> {after_display}"
    if row["detail"]:
        detail += f" ({row['detail']})"
    verdict = "REGRESSION" if row["regressed"] else "OK"
    return f"{pair}  [{row['kind']}]  {detail}  {verdict}"


def _validate_inputs(before_path: Path, after_path: Path, expected_dir: Path) -> int | None:
    """`None` when `before_path`/`after_path`/`expected_dir` are all usable;
    otherwise the exit code `main` should return (having already printed the
    reason to stderr)."""
    for label, path in (("before", before_path), ("after", after_path)):
        if not path.is_file():
            print(f"compare_eval_results.py: cannot read {label} file {path}", file=sys.stderr)
            return 2
    if not expected_dir.is_dir():
        print(f"compare_eval_results.py: expected dir not found: {expected_dir}", file=sys.stderr)
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", help="Path to the 'before' /agent-eval actuals JSON")
    parser.add_argument("after", help="Path to the 'after' /agent-eval actuals JSON")
    parser.add_argument(
        "--expected-dir",
        default="evals/expected",
        help=(
            "Directory of expected/*.json fixtures classifying each "
            "fixture/agent pair as a defect fixture (issueCount.min > 0 -- "
            "tracks true positives) or a clean fixture (issueCount.min == 0 "
            "-- tracks false positives). Default: evals/expected (mirrors "
            "eval_grade.py's own default)."
        ),
    )
    args = parser.parse_args(argv)

    before_path = Path(args.before)
    after_path = Path(args.after)
    expected_dir = Path(args.expected_dir)

    error_code = _validate_inputs(before_path, after_path, expected_dir)
    if error_code is not None:
        return error_code

    try:
        before = _load_json(before_path)
        after = _load_json(after_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"compare_eval_results.py: invalid JSON: {exc}", file=sys.stderr)
        return 2

    expected = _load_expected(expected_dir)
    if not expected:
        print(f"compare_eval_results.py: no usable expected/*.json found in {expected_dir}", file=sys.stderr)
        return 2

    rows, scope = compute_fixture_diffs(before, after, expected)
    if not rows:
        print(
            "compare_eval_results.py: no fixture/agent pair is present in both before and after files",
            file=sys.stderr,
        )
        return 2

    for row in rows:
        print(_format_row(row))

    total_skipped = scope["skippedNotComparable"] + scope["skippedUnclassified"]
    print(
        f"\ncompared {scope['compared']} pair(s); skipped {total_skipped} "
        f"({scope['skippedNotComparable']} not-in-both-runs, "
        f"{scope['skippedUnclassified']} unclassified/malformed)"
    )

    regressed = [row for row in rows if row["regressed"]]
    if regressed:
        print(f"\n{len(regressed)} regression(s) detected.")
        return 1
    print("\nNo regressions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
