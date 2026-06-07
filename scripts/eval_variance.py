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
    return _assemble(passes, trials, flap_threshold)


def aggregate_per_agent(expected_dir: Path, trials_root: Path, only: set,
                        flap_threshold: float = 0.0) -> dict:
    """Aggregate pass@k from a per-agent trial layout: ``<root>/<agent>/trial-*.json``.

    Each agent's trial files contain only that agent's verdicts, so grading is
    scoped to that agent (``run_grading(only={agent})``) — other agents' pairs are
    not counted as fails for this agent's trials. This is what the parallel harness
    produces, so the same K-trial pass@k feeds the trust-gated baseline write."""
    passes: dict[str, int] = defaultdict(int)
    trials: dict[str, int] = defaultdict(int)
    for agent in only:
        adir = trials_root / agent
        if not adir.is_dir():
            continue
        for tf in sorted(adir.glob("trial-*.json")):
            try:
                actuals = json.loads(tf.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            results, _ = run_grading(expected_dir, actuals, None, only={agent})
            for pair, passed, _fails in results:
                trials[pair] += 1
                if passed:
                    passes[pair] += 1
    return _assemble(passes, trials, flap_threshold)


def _assemble(passes: dict, trials: dict, flap_threshold: float) -> dict:
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


def write_baseline(report: dict, target_path, demote_below: float,
                   min_trials: int) -> tuple[list, list]:
    """Trust-gated baseline write (#230). A pair is **added** only when it passed
    every trial (pass@k == 1.0); **removed** only when it failed consistently
    (pass@k <= demote_below) over >= min_trials AND is not flaky. A flaky pair is
    never removed — it is quarantined instead (write_quarantine). So a single
    noisy trial (trials < min_trials) can add but never delete. Returns
    (added, removed) relative to the prior baseline."""
    from datetime import datetime, timezone
    target = Path(target_path)
    existing: set = set()
    if target.exists():
        try:
            existing = set(json.loads(target.read_text()).get("passing", []))
        except (OSError, json.JSONDecodeError):
            existing = set()
    by_pair = report["by_pair"]
    add = {p for p, d in by_pair.items() if d["pass_at_k"] >= 1.0}
    remove = {p for p, d in by_pair.items()
              if d["trials"] >= min_trials and d["pass_at_k"] <= demote_below
              and not d["flap"]}
    merged = (existing | add) - remove
    target.write_text(json.dumps({
        "_comment": "Regression baseline for the agent-eval CI gate (#99). "
                    "Trust-gated (#230): a pair is removed only when it failed "
                    "every trial (pass@k <= demote_below) over >= min_trials and "
                    "is not flaky; a flaky pair is quarantined, not removed; a pair "
                    "is added only when it passed all trials. Written by "
                    "eval_variance.py --write-baseline.",
        "provenance": "measured",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trials": report.get("trials", 0),
        "passing": sorted(merged),
    }, indent=2) + "\n")
    return sorted(add - existing), sorted(existing & remove)


def write_quarantine(report: dict, target_path) -> None:
    """Persist the flaky-pair set the #99 grader excludes from blocking (#231)."""
    from datetime import datetime, timezone
    detail = {p: {"pass_at_k": d["pass_at_k"], "trials": d["trials"]}
              for p, d in report["by_pair"].items() if d["flap"]}
    Path(target_path).write_text(json.dumps({
        "schema": "eval-variance/v1",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trials": report.get("trials", 0),
        "quarantine": report.get("quarantine", []),
        "detail": detail,
    }, indent=2, sort_keys=True) + "\n")


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
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--trials-dir",
                     help="directory of per-trial actuals JSON files (each a full "
                          "cross-agent actuals mapping)")
    src.add_argument("--trials-root",
                     help="per-agent layout <root>/<agent>/trial-*.json; needs --only")
    ap.add_argument("--only", default="",
                    help="comma-separated agents to read under --trials-root")
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("--flap-threshold", type=float, default=0.0,
                    help="minority-outcome fraction above which a pair is flaky")
    ap.add_argument("-o", "--out")
    ap.add_argument("--append", metavar="LOG",
                    help="append one metrics-only trend record")
    ap.add_argument("--write-baseline", metavar="PATH",
                    help="write a trust-gated regression baseline (#230)")
    ap.add_argument("--demote-below", type=float, default=0.0,
                    help="remove a pair only when pass@k <= this (default 0.0 = "
                         "failed every trial)")
    ap.add_argument("--min-trials", type=int, default=2,
                    help="a removal requires at least this many trials (default 2; "
                         "guards against deleting on a single noisy sample)")
    ap.add_argument("--quarantine-out", metavar="PATH",
                    help="write the flaky-pair quarantine the grader excludes (#231)")
    args = ap.parse_args(argv)

    if args.trials_root:
        only = {s.strip() for s in args.only.split(",") if s.strip()}
        if not only:
            print("error: --only is required with --trials-root", file=sys.stderr)
            return 2
        report = aggregate_per_agent(Path(args.expected_dir), Path(args.trials_root),
                                     only, args.flap_threshold)
    else:
        trials = _load_trials(Path(args.trials_dir))
        report = aggregate_trials(Path(args.expected_dir), trials, args.flap_threshold)

    out = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    elif not (args.write_baseline or args.quarantine_out):
        # Only dump the full report to stdout when not writing artifacts, so an
        # artifact-writing run stays quiet enough to read its summary line.
        print(out)
    if args.append:
        log = Path(args.append)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            fh.write(json.dumps(_slim(report), sort_keys=True) + "\n")
    if args.quarantine_out:
        write_quarantine(report, args.quarantine_out)
    if args.write_baseline:
        added, removed = write_baseline(report, args.write_baseline,
                                        args.demote_below, args.min_trials)
        print(f"Baseline (trust-gated) → {args.write_baseline}: "
              f"+{len(added)} / -{len(removed)} "
              f"(min_trials={args.min_trials}, demote_below={args.demote_below}); "
              f"{report['flaky_count']} quarantined")
        if added:
            print("  added:   " + ", ".join(added))
        if removed:
            print("  removed: " + ", ".join(removed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
