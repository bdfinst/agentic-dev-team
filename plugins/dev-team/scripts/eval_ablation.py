#!/usr/bin/env python3
"""Knowledge ablation analysis (#107) + agent-ablation analysis (#868).

Two related, deterministic (model-free) ablation reports live here:

1. **Knowledge ablation** (original, `--mode knowledge`, the default). Does a
   knowledge file earn its tokens? Run the eval corpus twice — once with the
   file AVAILABLE, once ABLATED (hidden) — and diff the grades. Pairs that
   PASSED with the knowledge but FAIL without it are the file's measured
   *retrieval value*.

2. **Agent ablation** (`--mode agent`, #868). Does removing a review agent
   from the orchestrator's inline-review roster change *integration-tier*
   pipeline outcomes? `/agent-eval --ablation <agent>` dispatches
   `scripts/run_integration_eval.py` twice per fixture (baseline: full
   roster; ablated: roster minus the named agent), each arm run K=3 trials
   (reusing the `eval_variance.py` pass@k machinery). This module grades the
   two arms' recorded actuals and computes the delta across three
   dimensions: issues caught at review checkpoints, `testCommands`
   pass/fail, and token cost. A failing baseline blocks any drop/retain
   verdict (the underlying signal is uninterpretable) per the acceptance
   criteria in issue #868.

Both modes are deterministic, model-free grading over already-recorded
actuals; live dispatch happens elsewhere (the `/agent-eval` skill /
`run_integration_eval.py`), never in this module.

Inputs (knowledge mode, `--mode knowledge`, default)
-----------------------------------------------------
--expected-dir DIR   Expected specs (default: evals/expected).
--baseline FILE      Actuals from the run WITH the knowledge available.
--ablated FILE       Actuals from the run with the knowledge ablated.
--knowledge NAME     Label for the ablated file (reporting only).
--only AGENT         Restrict grading to one agent (optional).
-o FILE              Write the report (default: stdout).

Inputs (agent mode, `--mode agent`, #868)
------------------------------------------
--expected-dir DIR          Expected specs (default: evals/expected).
--baseline-trials-dir DIR   Directory of the baseline arm's per-trial actuals
                            (`trial-*.json`, each the full actuals mapping
                            `run_integration_eval.py --out` writes).
--ablated-trials-dir DIR    Same, for the ablated arm.
--ablated-agent NAME        The review agent excluded in the ablated arm.
--model NAME                Model version used for both arms (REQUIRED —
                            deltas are model-dependent, per #868).
-o FILE                     Write the report (default: stdout).
--append LOG                Append one JSONL record (schema eval-ablation/v1)
                            to LOG, e.g. metrics/eval-ablation.jsonl.
--find-latest AGENT         Instead of computing a new report, read the
                            JSONL at --append (or -o) / a positional
                            --jsonl path and print the most recent record
                            for AGENT (or "null" if none) — used by
                            /harness-audit to cite evidence.
--jsonl PATH                JSONL file to search for --find-latest (default:
                            metrics/eval-ablation.jsonl).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


#: `eval_grade.py`/`eval_variance.py` are monorepo-dev-only eval-corpus
#: tooling (they read `evals/` fixtures that are never shipped), unlike this
#: module's own `--find-latest` mode — a generic JSONL reader with no
#: repo-shape assumption. #1653 moved this file into the plugin so a shipped
#: skill (harness-audit) can invoke `--find-latest` via `${CLAUDE_PLUGIN_ROOT}`,
#: but `--mode knowledge`/`--mode agent` still only make sense run from this
#: repo's own dev checkout, where the sibling modules below actually resolve.
#: Deferred (not module-level) so importing this file — or invoking
#: `--find-latest` — never requires them to be importable at all; a plugin
#: user has no `evals/` corpus and no reason to hit this path.
def _grading_deps():
    this_dir = Path(__file__).resolve().parent
    for candidate in (this_dir, _repo_root_scripts_dir(this_dir)):
        entry = str(candidate)
        if candidate.is_dir() and entry not in sys.path:
            sys.path.insert(0, entry)
    from eval_grade import run_grading
    from eval_variance import aggregate_trials

    return run_grading, aggregate_trials


def _repo_root_scripts_dir(this_dir: Path) -> Path:
    """The monorepo's own root `scripts/` dir, reached from this file's
    shipped location (`plugins/dev-team/scripts/`) by climbing three levels
    (`scripts` -> `dev-team` -> `plugins` -> repo root) then descending into
    `scripts/` again — where `eval_grade.py`/`eval_variance.py` still live,
    unmoved. Resolves to a real path only inside this repo's own checkout;
    harmless (simply not a directory) anywhere else."""
    return (this_dir / ".." / ".." / ".." / "scripts").resolve()


def _passing(expected_dir: Path, actuals: dict, only: set | None) -> set:
    run_grading, _ = _grading_deps()
    results, _ = run_grading(expected_dir, actuals, None, only)
    return {pair for pair, passed, _ in results if passed}


def ablation_impact(expected_dir: Path, baseline: dict, ablated: dict,
                    knowledge: str = "", only: set | None = None) -> dict:
    """Pairs that pass WITH the knowledge but fail WITHOUT it = retrieval value."""
    base_pass = _passing(expected_dir, baseline, only)
    abl_pass = _passing(expected_dir, ablated, only)
    dropped = sorted(base_pass - abl_pass)   # depended on the knowledge
    gained = sorted(abl_pass - base_pass)     # noise: passed only without it
    return {
        "schema": "knowledge-ablation/v1",
        "knowledge": knowledge,
        "retrieval_value": len(dropped),      # how many pairs the file held up
        "dropped_pairs": dropped,             # the evidence
        "spurious_gains": gained,             # should be empty; flags noise
        "verdict": ("earns its place" if dropped else
                    "no measured impact — removal/consolidation candidate"),
    }


def _load_trial_actuals(trials_dir: Path) -> list[dict]:
    """Load every `*.json` in trials_dir as one arm's per-trial actuals."""
    out = []
    for f in sorted(trials_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _flatten_integration_targets(actual: dict) -> list[tuple[str, dict]]:
    """Yield (fixture_stem::target, target_actual) for every integration entry
    in one trial's actuals mapping (the shape `run_integration_eval.py --out`
    writes: ``{stem: {"integration": {target: {"results", "tokens",
    "issues_caught"}}}}``)."""
    out = []
    for stem, block in actual.items():
        if not isinstance(block, dict):
            continue
        for target, tdata in block.get("integration", {}).items():
            if isinstance(tdata, dict):
                out.append((f"{stem}::{target}", tdata))
    return out


def summarize_arm(expected_dir: Path, trial_actuals: list[dict]) -> dict:
    """Deterministically summarize one ablation arm's K trials.

    `grade` is "pass" only if every fixture::target pair graded via the
    registered `integration` grader passed on **every** trial (pass@k ==
    1.0) — a conservative, reproducible bar; any flakiness or failure marks
    the arm "fail" so a shaky arm can never anchor a drop/retain verdict.
    `issues_caught` and `tokens` are the mean across trials (rounded);
    `test_commands` is taken from the first trial that recorded any (all
    trials target the same fixtures, so this is representative, not
    authoritative — the trial-level `grade` is what actually gates the
    verdict).
    """
    if not trial_actuals:
        return {"grade": "fail", "issues_caught": 0, "test_commands": [], "tokens": 0}

    _, aggregate_trials = _grading_deps()
    variance = aggregate_trials(expected_dir, trial_actuals)
    by_pair = variance.get("by_pair", {})
    # Scope the pass@k bar to the integration pairs this arm actually
    # dispatched. aggregate_trials grades the WHOLE expected corpus, so the
    # unit-tier fixtures that an integration arm never runs would otherwise
    # report pass_at_k 0.0 and force every arm — baseline included — to "fail",
    # making every ablation "baseline failed — inconclusive". Only the
    # fixture(s) under ablation gate the arm verdict.
    scoped_pairs: set[str] = set()
    for actual in trial_actuals:
        for pair, _tdata in _flatten_integration_targets(actual):
            scoped_pairs.add(pair)
    all_pass = bool(scoped_pairs) and all(
        pair in by_pair and by_pair[pair]["pass_at_k"] >= 1.0
        for pair in scoped_pairs
    )

    issues_totals: list[int] = []
    token_totals: list[int] = []
    test_commands: list[dict] = []
    for actual in trial_actuals:
        issues_sum = 0
        tokens_sum = 0
        for _pair, tdata in _flatten_integration_targets(actual):
            issues_sum += int(tdata.get("issues_caught", 0) or 0)
            tokens_sum += int(tdata.get("tokens", 0) or 0)
            if not test_commands:
                test_commands.extend(
                    {"command": r.get("command"), "exit_code": r.get("exit_code")}
                    for r in tdata.get("results", []) or []
                    if isinstance(r, dict)
                )
        issues_totals.append(issues_sum)
        token_totals.append(tokens_sum)

    mean_issues = round(sum(issues_totals) / len(issues_totals)) if issues_totals else 0
    mean_tokens = round(sum(token_totals) / len(token_totals)) if token_totals else 0

    return {
        "grade": "pass" if all_pass else "fail",
        "issues_caught": mean_issues,
        "test_commands": test_commands,
        "tokens": mean_tokens,
    }


def _passed_command_count(arm: dict) -> int:
    return sum(1 for c in arm.get("test_commands", []) if c.get("exit_code") == 0)


def agent_ablation_report(
    expected_dir: Path,
    baseline_trials: list[dict],
    ablated_trials: list[dict],
    ablated_agent: str,
    model: str,
    fixtures: list[str] | None = None,
) -> dict:
    """Grade both arms and compute the three-dimension delta (#868).

    A failing baseline blocks any drop/retain claim (acceptance criterion
    "failing-baseline-blocks-delta-claims"): the delta is still reported for
    visibility, but `verdict` is forced to "baseline failed — inconclusive"
    regardless of what the ablated arm shows.
    """
    baseline = summarize_arm(expected_dir, baseline_trials)
    ablated = summarize_arm(expected_dir, ablated_trials)

    delta = {
        "issues_caught": ablated["issues_caught"] - baseline["issues_caught"],
        "test_commands_passed": _passed_command_count(ablated)
        - _passed_command_count(baseline),
        "tokens": ablated["tokens"] - baseline["tokens"],
    }

    if baseline["grade"] != "pass":
        verdict = "baseline failed — inconclusive"
    elif delta["issues_caught"] == 0 and delta["test_commands_passed"] == 0:
        verdict = "no measured impact — supports drop"
    else:
        verdict = "agent is load-bearing — retain"

    if fixtures is None:
        stems = set()
        for actual in baseline_trials + ablated_trials:
            stems.update(k for k in actual if isinstance(actual.get(k), dict))
        fixtures = sorted(stems)

    return {
        "schema": "eval-ablation/v1",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ablated_agent": ablated_agent,
        "fixtures": fixtures,
        "model": model,
        "baseline": baseline,
        "ablated": ablated,
        "delta": delta,
        "verdict": verdict,
    }


def find_latest_ablation_record(jsonl_path: Path, agent: str) -> dict | None:
    """Return the most recent `eval-ablation/v1` record for `agent`, or None.

    Used by `/harness-audit` (Step 3) to cite causal evidence for a
    drop-candidate agent instead of correlational usage data alone.
    """
    if not jsonl_path.exists():
        return None
    latest: dict | None = None
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("ablated_agent") != agent:
            continue
        if latest is None or record.get("recorded_at", "") >= latest.get(
            "recorded_at", ""
        ):
            latest = record
    return latest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["knowledge", "agent"], default="knowledge")
    ap.add_argument("--expected-dir", default="evals/expected")
    # knowledge mode
    ap.add_argument("--baseline")
    ap.add_argument("--ablated")
    ap.add_argument("--knowledge", default="")
    ap.add_argument("--only")
    # agent mode (#868)
    ap.add_argument("--baseline-trials-dir")
    ap.add_argument("--ablated-trials-dir")
    ap.add_argument("--ablated-agent")
    ap.add_argument("--model", help="model version used for both arms (required "
                    "for --mode agent — deltas are model-dependent)")
    ap.add_argument("--fixtures", help="comma-separated fixture stems actually "
                    "exercised (reporting only; auto-detected if omitted)")
    ap.add_argument("--append", metavar="LOG",
                    help="append the report as one JSONL line to LOG")
    ap.add_argument("--find-latest", metavar="AGENT",
                    help="print the most recent eval-ablation/v1 record for "
                    "AGENT from --jsonl (or 'null'); no report is computed")
    ap.add_argument("--jsonl", default="metrics/eval-ablation.jsonl",
                    help="JSONL file for --find-latest (default: "
                    "metrics/eval-ablation.jsonl)")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)

    if args.find_latest:
        record = find_latest_ablation_record(Path(args.jsonl), args.find_latest)
        print(json.dumps(record) if record else "null")
        return 0

    if args.mode == "agent":
        if not args.model:
            print("error: --mode agent requires --model (deltas are "
                  "model-dependent, #868)", file=sys.stderr)
            return 2
        if not (args.baseline_trials_dir and args.ablated_trials_dir
                and args.ablated_agent):
            print("error: --mode agent requires --baseline-trials-dir, "
                  "--ablated-trials-dir, and --ablated-agent", file=sys.stderr)
            return 2
        baseline_trials = _load_trial_actuals(Path(args.baseline_trials_dir))
        ablated_trials = _load_trial_actuals(Path(args.ablated_trials_dir))
        fixtures = (
            [s.strip() for s in args.fixtures.split(",") if s.strip()]
            if args.fixtures else None
        )
        report = agent_ablation_report(
            Path(args.expected_dir), baseline_trials, ablated_trials,
            args.ablated_agent, args.model, fixtures,
        )
        out = json.dumps(report, indent=2, sort_keys=True)
        if args.out:
            Path(args.out).write_text(out + "\n")
        else:
            print(out)
        if args.append:
            with open(args.append, "a") as fh:
                fh.write(json.dumps(report, sort_keys=True) + "\n")
        return 0

    if not (args.baseline and args.ablated):
        print("error: --mode knowledge requires --baseline and --ablated",
              file=sys.stderr)
        return 2
    baseline = json.loads(Path(args.baseline).read_text())
    ablated = json.loads(Path(args.ablated).read_text())
    only = {args.only} if args.only else None
    report = ablation_impact(Path(args.expected_dir), baseline, ablated,
                             args.knowledge, only)
    out = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
