#!/usr/bin/env python3
"""Runtime cost/token meter for dispatched work (issue #102).

PostToolUse hooks do NOT carry token usage in Claude Code; the canonical source
is the session transcript JSONL, where each assistant message records a `usage`
block (input/output/cache tokens). Every hook payload includes `transcript_path`,
so a Stop hook can hand this script the transcript to parse. This converts token
usage to dollars via the named instrument knowledge/model-pricing.json (#102 is
why that table exists) and writes an append-only metrics log.

Subcommands
-----------
report   --transcript T [--json]
         Parse a transcript and print tokens + cost per agent and per model,
         plus the session total. This is the acceptance command: "after a run,
         print actual tokens spent per agent and total."

record   --transcript T --log metrics/cost-metering.jsonl
         Append one session-summary line to the append-only metrics log
         (follows the metrics/config-changelog.jsonl convention). Used by the
         Stop hook. Idempotent on directory creation; never errors out loudly.

regression --log metrics/cost-metering.jsonl [--tolerance 0.5]
         Compare the most recent session's total cost against the rolling mean
         of prior sessions; exit 1 if it exceeds mean * (1 + tolerance). The
         CI/regression hook the acceptance criteria asks for.

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


def parse_transcript(path: Path, pricing: dict) -> dict:
    """Aggregate usage by agent and by model. Returns a summary dict."""
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    totals = {"input_tokens": 0, "output_tokens": 0,
              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
              "cost_usd": 0.0, "messages": 0}
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

        rate = _rate(pricing, model)
        cost = _cost(usage, rate, pricing) if rate else 0.0
        if not rate and model != "unknown":
            unpriced_models.add(model)

        for bucket, key in ((by_agent, agent), (by_model, model)):
            b = bucket.setdefault(key, {"input_tokens": 0, "output_tokens": 0,
                                        "cache_creation_input_tokens": 0,
                                        "cache_read_input_tokens": 0,
                                        "cost_usd": 0.0, "messages": 0})
            for f in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens"):
                b[f] += usage.get(f, 0) or 0
            b["cost_usd"] = round(b["cost_usd"] + cost, 6)
            b["messages"] += 1

        for f in ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens"):
            totals[f] += usage.get(f, 0) or 0
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
        totals["messages"] += 1

    return {"by_agent": by_agent, "by_model": by_model, "totals": totals,
            "unpriced_models": sorted(unpriced_models)}


def _print_report(summary: dict) -> None:
    t = summary["totals"]
    print(f"# Cost meter — {t['messages']} assistant message(s)\n")
    print(f"{'AGENT':<28} {'IN':>10} {'OUT':>10} {'COST $':>10}")
    print("-" * 60)
    for agent, b in sorted(summary["by_agent"].items(),
                           key=lambda kv: -kv[1]["cost_usd"]):
        print(f"{agent:<28} {b['input_tokens']:>10} {b['output_tokens']:>10} "
              f"{b['cost_usd']:>10.4f}")
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
    line = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transcript": tpath.name,
        "total": summary["totals"],
        "by_agent": {a: {"cost_usd": b["cost_usd"],
                         "input_tokens": b["input_tokens"],
                         "output_tokens": b["output_tokens"]}
                     for a, b in summary["by_agent"].items()},
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
    mean = sum(prior) / len(prior)
    limit = mean * (1 + args.tolerance)
    print(f"latest=${latest:.4f}  rolling-mean(prior {len(prior)})=${mean:.4f}  "
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

    args = ap.parse_args(argv)
    pricing = _load_pricing(Path(args.pricing))
    return {"report": cmd_report, "record": cmd_record,
            "regression": cmd_regression}[args.cmd](args, pricing)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
