#!/usr/bin/env python3
"""Eval variance & saturation aggregator (#103).

`/agent-eval --trials K` dispatches each fixture to its agents K times (that's
the live, model-spending part). This script is the **deterministic, model-free**
half: given the K trials' recorded actuals (the same `actuals` JSON
`eval_grade.py` consumes), it computes per-`fixture::agent` **pass@k** and **flap
rate**, a per-agent stability summary, and a **quarantine** list of flaky pairs.

Why it matters (#103): "agent quality without a variance number is a vibe." A
fixture that flaps (sometimes pass, sometimes fail) should *inform* the #99 CI
gate, not silently block it. This persists that signal over time.

Inputs
------
--trials-dir DIR   Directory of per-trial actuals files (`*.json`); one file per
                   trial, each the actuals mapping eval_grade.py grades.
--expected-dir DIR Expected specs (default: evals/expected).
-o FILE            Write the full variance report (default: stdout).
--append LOG       Append one metrics-only trend record (counts/ratios only).

Reuses `eval_grade.run_grading`, so a pair passes here iff it passes the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_grade import run_grading  # noqa: E402


def aggregate_trials(expected_dir: Path, trial_actuals: list[dict],
                     flap_threshold: float = 0.0) -> dict:
    """Grade each trial's actuals and aggregate pass@k / flap per pair.

    A pair is *flaky* when it neither always passes nor always fails across the
    trials (instability strictly greater than `flap_threshold`, expressed as the
    fraction of the minority outcome)."""
    passes: dict[str, int] = defaultdict(int)
    trials: dict[str, int] = defaultdict(int)
    for actuals in trial_actuals:
        results, _ = run_grading(expected_dir, actuals, None)
        for pair, passed, _fails in results:
            trials[pair] += 1
            if passed:
                passes[pair] += 1

    by_pair: dict[str, dict] = {}
    flaky: list[str] = []
    for pair in sorted(trials):
        t, p = trials[pair], passes[pair]
        minority = min(p, t - p) / t if t else 0.0
        flap = minority > flap_threshold
        by_pair[pair] = {"trials": t, "passes": p,
                         "pass_at_k": round(p / t, 4) if t else 0.0,
                         "flap": flap}
        if flap:
            flaky.append(pair)

    by_agent: dict[str, dict] = defaultdict(
        lambda: {"pairs": 0, "flaky_fixtures": 0, "_sum": 0.0})
    for pair, d in by_pair.items():
        agent = pair.split("::", 1)[1] if "::" in pair else pair
        a = by_agent[agent]
        a["pairs"] += 1
        a["_sum"] += d["pass_at_k"]
        if d["flap"]:
            a["flaky_fixtures"] += 1
    agent_summary = {
        a: {"pairs": v["pairs"], "flaky_fixtures": v["flaky_fixtures"],
            "mean_pass_at_k": round(v["_sum"] / v["pairs"], 4) if v["pairs"] else 0.0}
        for a, v in sorted(by_agent.items())
    }

    return {
        "schema": "eval-variance/v1",
        "trials": max(trials.values()) if trials else 0,
        "pairs_evaluated": len(by_pair),
        "flaky_count": len(flaky),
        "quarantine": flaky,  # flaky fixtures inform — they must not block #99
        "by_agent": agent_summary,
        "by_pair": by_pair,
    }


def _load_trials(trials_dir: Path) -> list[dict]:
    out = []
    for f in sorted(trials_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _slim(report: dict) -> dict:
    from datetime import datetime, timezone
    agents = report.get("by_agent", {})
    mean = (round(sum(a["mean_pass_at_k"] for a in agents.values()) / len(agents), 4)
            if agents else 0.0)
    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": "eval-variance/v1",
        "trials": report.get("trials", 0),
        "pairs_evaluated": report.get("pairs_evaluated", 0),
        "flaky_count": report.get("flaky_count", 0),
        "mean_pass_at_k": mean,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials-dir", required=True,
                    help="directory of per-trial actuals JSON files")
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("--flap-threshold", type=float, default=0.0,
                    help="minority-outcome fraction above which a pair is flaky")
    ap.add_argument("-o", "--out")
    ap.add_argument("--append", metavar="LOG",
                    help="append one metrics-only trend record")
    args = ap.parse_args(argv)

    trials = _load_trials(Path(args.trials_dir))
    report = aggregate_trials(Path(args.expected_dir), trials, args.flap_threshold)
    out = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    if args.append:
        log = Path(args.append)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            fh.write(json.dumps(_slim(report), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
