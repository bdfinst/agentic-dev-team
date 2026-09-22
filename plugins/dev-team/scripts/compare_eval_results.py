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
read as its true-positive count. A block whose `issueCount.min == 0` is a
**clean fixture** (built to contain nothing worth flagging) -- the number of
issues reported against it is read as its false-positive count. This is a
fixture-level proxy, not a per-issue correctness judgment: it assumes every
issue reported on a defect fixture is (part of) the injected defect it was
built to catch, and every issue reported on a clean fixture is, by
construction, spurious.

Regression rule
----------------
For a defect fixture: `after`'s issue count < `before`'s issue count is a
true-positive-count regression. For a clean fixture: `after`'s issue count >
`before`'s issue count is a false-positive-count regression. Either is a hard
fail for this gate.

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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_expected(expected_dir: Path) -> dict[str, dict]:
    """`{stem: {agent: espec, ...}, ...}` for every `expected/*.json` under
    `expected_dir` that declares an `agents` block. Malformed expected files
    are skipped rather than raising -- this script's job is to compare
    result files, not to re-run `eval_grade.py --check-corpus`."""
    out: dict[str, dict] = {}
    for f in sorted(expected_dir.glob("*.json")):
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        agents = spec.get("agents")
        if isinstance(agents, dict) and agents:
            out[f.stem] = agents
    return out


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


def compute_fixture_diffs(before: dict, after: dict, expected: dict) -> list[dict]:
    """One row per `(fixture stem, agent)` pair declared in `expected`, for
    every pair present in both `before` and `after`. Each row is
    `{"fixture", "agent", "kind": "defect"|"clean",
    "truePositivesBefore"|None, "truePositivesAfter"|None,
    "falsePositivesBefore"|None, "falsePositivesAfter"|None, "regressed"}`
    -- only the pair of fields matching `kind` is populated; the other pair
    is `None` (not applicable to that fixture's classification)."""
    rows: list[dict] = []
    for stem, agents in expected.items():
        for agent, espec in agents.items():
            if not isinstance(espec, dict):
                continue
            issue_count = espec.get("issueCount") or {}
            is_defect_fixture = issue_count.get("min", 0) > 0

            before_n = _issue_count(before, stem, agent)
            after_n = _issue_count(after, stem, agent)
            if before_n is None or after_n is None:
                continue  # not recorded in both runs -- not comparable

            if is_defect_fixture:
                regressed = after_n < before_n
                row = {
                    "fixture": stem,
                    "agent": agent,
                    "kind": "defect",
                    "truePositivesBefore": before_n,
                    "truePositivesAfter": after_n,
                    "falsePositivesBefore": None,
                    "falsePositivesAfter": None,
                    "regressed": regressed,
                }
            else:
                regressed = after_n > before_n
                row = {
                    "fixture": stem,
                    "agent": agent,
                    "kind": "clean",
                    "truePositivesBefore": None,
                    "truePositivesAfter": None,
                    "falsePositivesBefore": before_n,
                    "falsePositivesAfter": after_n,
                    "regressed": regressed,
                }
            rows.append(row)
    rows.sort(key=lambda r: (r["fixture"], r["agent"]))
    return rows


def _format_row(row: dict) -> str:
    pair = f"{row['fixture']}::{row['agent']}"
    if row["kind"] == "defect":
        detail = f"TP: {row['truePositivesBefore']} -> {row['truePositivesAfter']}"
    else:
        detail = f"FP: {row['falsePositivesBefore']} -> {row['falsePositivesAfter']}"
    verdict = "REGRESSION" if row["regressed"] else "OK"
    return f"{pair}  [{row['kind']}]  {detail}  {verdict}"


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

    for label, path in (("before", before_path), ("after", after_path)):
        if not path.is_file():
            print(f"compare_eval_results.py: cannot read {label} file {path}", file=sys.stderr)
            return 2
    if not expected_dir.is_dir():
        print(f"compare_eval_results.py: expected dir not found: {expected_dir}", file=sys.stderr)
        return 2

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

    rows = compute_fixture_diffs(before, after, expected)
    if not rows:
        print(
            "compare_eval_results.py: no fixture/agent pair is present in both before and after files",
            file=sys.stderr,
        )
        return 2

    for row in rows:
        print(_format_row(row))

    regressed = [row for row in rows if row["regressed"]]
    if regressed:
        print(f"\n{len(regressed)} regression(s) detected.")
        return 1
    print("\nNo regressions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
