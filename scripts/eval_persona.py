"""Persona-vs-context-boundary analysis (#110).

The repo's sharpest claim is that the value of sub-agents is *context isolation*,
not *persona specialization*. This tests it empirically: run each agent with its
persona prose ON vs OFF (same fixtures, same trials) and compare pass@k. A delta
only counts as REAL when it exceeds the noise band — i.e. neither run flapped on
that agent's fixtures (variance from #103).

Deterministic, model-free half: given two dirs of trial actuals (persona-on,
persona-off), it reuses eval_variance.aggregate_trials and reports the per-agent
delta plus whether it is trustworthy. The live on/off runs (and the check that the
persona prose was genuinely stripped) are run-persona-eval.sh's job.

Inputs
------
--on-trials DIR    trial actuals from the persona-ON runs.
--off-trials DIR   trial actuals from the persona-OFF runs.
--expected-dir DIR expected specs (default: evals/expected).
-o FILE            report (default: stdout).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_variance import aggregate_trials, _load_trials  # noqa: E402


def persona_delta(expected_dir: Path, on_trials: list[dict],
                  off_trials: list[dict]) -> dict:
    on = aggregate_trials(expected_dir, on_trials)["by_agent"]
    off = aggregate_trials(expected_dir, off_trials)["by_agent"]
    agents = sorted(set(on) | set(off))
    rows = {}
    helps = hurts = noeffect = 0
    for a in agents:
        o = on.get(a, {"mean_pass_at_k": 0.0, "flaky_fixtures": 0})
        f = off.get(a, {"mean_pass_at_k": 0.0, "flaky_fixtures": 0})
        delta = round(o["mean_pass_at_k"] - f["mean_pass_at_k"], 4)
        # The delta is trustworthy only if neither run flapped on this agent —
        # otherwise it's inside the variance band (noise), not signal.
        flapped = o["flaky_fixtures"] > 0 or f["flaky_fixtures"] > 0
        real = (delta != 0.0) and not flapped
        if not real:
            verdict = "within noise band" if flapped else "no effect"
            noeffect += 1
        elif delta > 0:
            verdict = "persona ADDS detection value"
            helps += 1
        else:
            verdict = "persona REDUCES detection value"
            hurts += 1
        rows[a] = {
            "mean_pass_persona_on": o["mean_pass_at_k"],
            "mean_pass_persona_off": f["mean_pass_at_k"],
            "delta": delta,
            "flapped": flapped,
            "real": real,
            "verdict": verdict,
        }
    return {
        "schema": "persona-delta/v1",
        "agents_evaluated": len(agents),
        "persona_helps": helps,
        "persona_hurts": hurts,
        "no_effect_or_noise": noeffect,
        "by_agent": rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--on-trials", required=True)
    ap.add_argument("--off-trials", required=True)
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)
    report = persona_delta(Path(args.expected_dir),
                           _load_trials(Path(args.on_trials)),
                           _load_trials(Path(args.off_trials)))
    out = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
