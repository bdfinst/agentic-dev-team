#!/usr/bin/env python3
"""Runtime cost/token meter for dispatched work (issues #102, #134).

PostToolUse hooks do NOT carry token usage in Claude Code; the canonical source
is the session transcript JSONL, where each assistant message records a `usage`
block (input/output/cache tokens). Every hook payload includes `transcript_path`,
so a Stop hook can hand this script the transcript to parse. This converts token
usage to dollars via the named instrument knowledge/model-pricing.json (#102 is
why that table exists) and writes an append-only metrics log.

Attribution dimensions (#134)
------------------------------
Beyond per-agent and per-model, spend is attributed to:
  * the invoking COMMAND/skill, read from the transcript's `attributionSkill`
    field (falls back to "untagged" when a record carries no skill tag), and
  * the fix-loop ITERATION, read from a `fixLoopIteration` / `reviewIteration`
    / `iteration` marker on the record. The transcript has no native iteration
    boundary, so the review->fix cycle is expected to stamp this marker on its
    dispatches; absent the marker, usage degrades to the "unattributed" bucket
    rather than being silently lost.
  * the orchestration PHASE (specs/plan/build/review), from an explicit
    `orchestrationPhase` marker when present, else derived from the command via
    a static command->phase map (#139); unmapped commands fall into "other".

Privacy boundary (#134, req 6)
------------------------------
This meter persists ONLY token counts, dollar amounts, model identifiers, agent
identifiers, the skill/command tag, and the iteration index. It never reads or
records prompt text, code, file paths, or tool payloads from the transcript —
only the `usage`/`model`/attribution fields. The append-only metrics log is a
metrics-only artifact by construction.

Subcommands
-----------
report   --transcript T [--json]
         Parse a transcript and print tokens + cost per agent, per model, per
         command, and per fix-loop iteration, plus the session total. The
         acceptance command: "after a run, print actual tokens spent."

record   --transcript T --log metrics/cost-metering.jsonl
         Append one session-summary line to the append-only metrics log
         (follows the metrics/config-changelog.jsonl convention). Used by the
         Stop hook. Idempotent on directory creation; never errors out loudly.

regression --log metrics/cost-metering.jsonl [--tolerance 0.5] [--window N]
         Compare the most recent session's total cost against the rolling mean
         of prior sessions; exit 1 if it exceeds mean * (1 + tolerance). With
         --window N the baseline is the mean of only the N most recent prior
         sessions (a windowed rolling baseline) instead of all-time mean.

The transcript schema is read defensively (usage may sit on the record or under
`message`; model + agent attribution likewise), so it tolerates schema drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# hooks/lib/cost_meter.py -> plugin root is three parents up.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PRICING = _PLUGIN_ROOT / "knowledge/model-pricing.json"


def _load_pricing(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data


def _rate(pricing: dict, model: str) -> dict | None:
    models = pricing.get("models", {})
    if model in models:
        return models[model]
    alias = pricing.get("aliases", {}).get(model)
    if alias and alias in models:
        return models[alias]
    return None


def _dig(rec: dict, *keys: str):
    """Return the first present key on rec or rec['message']."""
    for src in (rec, rec.get("message", {}) if isinstance(rec.get("message"), dict) else {}):
        for k in keys:
            if k in src and src[k] is not None:
                return src[k]
    return None


def _cost(usage: dict, rate: dict, pricing: dict) -> float:
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    in_rate = rate["input"]
    return (
        inp / 1e6 * in_rate
        + out / 1e6 * rate["output"]
        + cw / 1e6 * in_rate * pricing.get("cache_write_multiplier", 1.25)
        + cr / 1e6 * in_rate * pricing.get("cache_read_multiplier", 0.1)
    )


_TOKEN_FIELDS = ("input_tokens", "output_tokens",
                 "cache_creation_input_tokens", "cache_read_input_tokens")


def _new_bucket() -> dict:
    return {f: 0 for f in _TOKEN_FIELDS} | {"cost_usd": 0.0, "messages": 0}


# Orchestration-phase mapping (#139): which command/skill belongs to which of
# the specs -> plan -> build -> review phases. Commands not in the map (or
# untagged records) fall into the "other" phase rather than being lost.
_PHASE_BY_COMMAND = {
    "specs": "specs",
    "plan": "plan", "issues-from-plan": "plan",
    "build": "build", "apply-fixes": "build", "continue": "build",
    "code-review": "review", "review": "review", "review-agent": "review",
    "test-design": "review", "test-health": "review", "agent-eval": "review",
    "review-summary": "review",
}


def _phase_for(command: str) -> str:
    return _PHASE_BY_COMMAND.get(command, "other")


def parse_transcript(path: Path, pricing: dict) -> dict:
    """Aggregate usage by agent, model, command, fix-loop iteration, phase."""
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_command: dict[str, dict] = {}
    by_iteration: dict[str, dict] = {}
    by_phase: dict[str, dict] = {}
    totals = _new_bucket()
    unpriced_models: set[str] = set()

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = _dig(rec, "usage")
        if not isinstance(usage, dict):
            continue
        model = _dig(rec, "model") or "unknown"
        # Sub-agent attribution: agent_type/agent_id present for subagents,
        # else the main orchestrator thread.
        agent = _dig(rec, "agent_type", "subagent_type", "agent_id") or "orchestrator"
        # Invoking command/skill (#134): the transcript's attributionSkill tag.
        command = _dig(rec, "attributionSkill", "attribution_skill") or "untagged"
        # Fix-loop iteration marker (#134): stamped by the review->fix cycle;
        # absent markers degrade to "unattributed" rather than being lost.
        iteration = _dig(rec, "fixLoopIteration", "reviewIteration", "iteration")
        iteration = str(iteration) if iteration is not None else "unattributed"
        # Orchestration phase (#139): an explicit phase marker wins; otherwise
        # derive it from the command -> phase map.
        phase = _dig(rec, "orchestrationPhase", "phase") or _phase_for(command)

        rate = _rate(pricing, model)
        cost = _cost(usage, rate, pricing) if rate else 0.0
        if not rate and model != "unknown":
            unpriced_models.add(model)

        for bucket, key in ((by_agent, agent), (by_model, model),
                            (by_command, command), (by_iteration, iteration),
                            (by_phase, phase)):
            b = bucket.setdefault(key, _new_bucket())
            for f in _TOKEN_FIELDS:
                b[f] += usage.get(f, 0) or 0
            b["cost_usd"] = round(b["cost_usd"] + cost, 6)
            b["messages"] += 1

        for f in _TOKEN_FIELDS:
            totals[f] += usage.get(f, 0) or 0
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
        totals["messages"] += 1

    return {"by_agent": by_agent, "by_model": by_model,
            "by_command": by_command, "by_iteration": by_iteration,
            "by_phase": by_phase,
            "totals": totals, "unpriced_models": sorted(unpriced_models)}


def _print_dimension(title: str, bucket: dict) -> None:
    if not bucket:
        return
    print(f"\n{title:<28} {'IN':>10} {'OUT':>10} {'COST $':>10}")
    print("-" * 60)
    for key, b in sorted(bucket.items(), key=lambda kv: -kv[1]["cost_usd"]):
        print(f"{key:<28} {b['input_tokens']:>10} {b['output_tokens']:>10} "
              f"{b['cost_usd']:>10.4f}")


def _print_report(summary: dict) -> None:
    t = summary["totals"]
    print(f"# Cost meter — {t['messages']} assistant message(s)")
    _print_dimension("AGENT", summary["by_agent"])
    _print_dimension("COMMAND", summary.get("by_command", {}))
    _print_dimension("ORCHESTRATION PHASE", summary.get("by_phase", {}))
    # Iteration ordered numerically where possible (1, 2, ... then unattributed).
    _print_dimension("FIX-LOOP ITERATION", summary.get("by_iteration", {}))
    print("-" * 60)
    print(f"{'TOTAL':<28} {t['input_tokens']:>10} {t['output_tokens']:>10} "
          f"{t['cost_usd']:>10.4f}")
    if summary["unpriced_models"]:
        print(f"\n⚠ no pricing for: {', '.join(summary['unpriced_models'])} "
              f"(add to knowledge/model-pricing.json)")


def cmd_report(args, pricing) -> int:
    summary = parse_transcript(Path(args.transcript), pricing)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_report(summary)
    return 0


def cmd_record(args, pricing) -> int:
    tpath = Path(args.transcript)
    if not tpath.is_file():
        return 0  # fail-open: hook must never break the session
    summary = parse_transcript(tpath, pricing)
    from datetime import datetime, timezone
    def _slim(bucket: dict) -> dict:
        return {k: {"cost_usd": b["cost_usd"],
                    "input_tokens": b["input_tokens"],
                    "output_tokens": b["output_tokens"]}
                for k, b in bucket.items()}

    line = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transcript": tpath.name,
        "total": summary["totals"],
        "by_agent": _slim(summary["by_agent"]),
        "by_command": _slim(summary["by_command"]),
        "by_iteration": _slim(summary["by_iteration"]),
        "by_phase": _slim(summary["by_phase"]),
    }
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(line) + "\n")
    return 0


def cmd_regression(args, pricing) -> int:
    log = Path(args.log)
    if not log.is_file():
        print("no metrics log yet; nothing to compare")
        return 0
    entries = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    costs = [e.get("total", {}).get("cost_usd", 0.0) for e in entries]
    if len(costs) < 2:
        print(f"only {len(costs)} session(s) logged; need >=2 to compare")
        return 0
    latest = costs[-1]
    prior = costs[:-1]
    # Windowed rolling baseline (#134): mean of only the N most recent priors.
    window = getattr(args, "window", 0) or 0
    if window > 0:
        prior = prior[-window:]
    mean = sum(prior) / len(prior)
    limit = mean * (1 + args.tolerance)
    win_label = f"window {len(prior)}" if window > 0 else f"prior {len(prior)}"
    print(f"latest=${latest:.4f}  rolling-mean({win_label})=${mean:.4f}  "
          f"limit(+{int(args.tolerance*100)}%)=${limit:.4f}")
    if mean > 0 and latest > limit:
        print(f"COST REGRESSION: latest ${latest:.4f} exceeds limit ${limit:.4f}")
        return 1
    print("no cost regression")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pricing", default=str(_DEFAULT_PRICING))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("report"); p.add_argument("--transcript", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("record"); p.add_argument("--transcript", required=True)
    p.add_argument("--log", default="metrics/cost-metering.jsonl")
    p = sub.add_parser("regression"); p.add_argument("--log", default="metrics/cost-metering.jsonl")
    p.add_argument("--tolerance", type=float, default=0.5)
    p.add_argument("--window", type=int, default=0,
                   help="baseline = mean of the N most recent prior sessions "
                        "(0 = all-time mean)")

    args = ap.parse_args(argv)
    pricing = _load_pricing(Path(args.pricing))
    return {"report": cmd_report, "record": cmd_record,
            "regression": cmd_regression}[args.cmd](args, pricing)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
