#!/usr/bin/env python3
"""Runtime cost/token meter for dispatched work (issues #102, #134).

PostToolUse hooks do NOT carry token usage in Claude Code; the canonical source
is the session transcript JSONL, where each assistant message records a `usage`
block (input/output/cache tokens). Every hook payload includes `transcript_path`,
so a Stop hook can hand this script the transcript to parse. This converts token
usage to dollars via the named instrument knowledge/model-pricing.json (#102 is
why that table exists) and writes an append-only metrics log.

Attribution dimensions (#102, #170)
-----------------------------------
Attribution is limited to what the harness actually records on transcript
records — verified empirically (#170). Spend is attributed to:
  * the MODEL (`message.model`), and
  * the THREAD: main-loop vs subagent, from the native top-level `isSidechain`
    flag (true on subagent/sidechain turns).
  * plus the session TOTAL.

What is deliberately NOT attributed, and why (#170): per-command, per-phase, and
per-fix-loop-iteration attribution were attempted via `attributionSkill` /
`orchestrationPhase` / `fixLoopIteration` markers, but **the Claude Code harness
authors the transcript and exposes none of those fields** (0/312 in a real
transcript), and a plugin has no write-path into the transcript. Those buckets
were therefore always inert ("untagged"/"other"/"unattributed") and have been
removed rather than ship misleading empty dimensions. Re-deriving them would
require fragile heuristics (correlating Stop-hook timestamps with command
boundaries) and is out of scope.

Privacy boundary
----------------
This meter persists ONLY token counts, dollar amounts, model identifiers, and
the main/subagent thread flag. It never reads or records prompt text, code, file
paths, or tool payloads from the transcript — only the `usage`/`model`/
`isSidechain` fields. The append-only metrics log is a metrics-only artifact by
construction.

Subcommands
-----------
report   --transcript T [--json]
         Parse a transcript and print tokens + cost per model and per thread
         (main vs subagent), plus the session total. The acceptance command:
         "after a run, print actual tokens spent."

record   --transcript T --log metrics/cost-metering.jsonl
         Append one session-summary line to the append-only metrics log
         (follows the metrics/config-changelog.jsonl convention). Used by the
         Stop hook. Idempotent on directory creation; never errors out loudly.

regression --log metrics/cost-metering.jsonl [--tolerance 0.5] [--window N]
         Compare the most recent session's total cost against the rolling mean
         of prior sessions; exit 1 if it exceeds mean * (1 + tolerance). With
         --window N the baseline is the mean of only the N most recent prior
         sessions (a windowed rolling baseline) instead of all-time mean.

pace     --log metrics/cost-metering.jsonl [--budget B] [--period-days 30]
         [--window-days 7]
         Account-level pace guidance (#142): cumulative spend over a rolling
         window, the implied daily rate, and the projected spend for a billing
         period. With --budget it flags when the current pace would exhaust the
         budget and suggests dropping a model tier for the rest of the window.

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


def parse_transcript(path: Path, pricing: dict) -> dict:
    """Aggregate transcript usage by model and by thread (main vs subagent).

    Only dimensions the harness actually records are attributed (#170): the
    model (`message.model`) and the main/subagent split (native top-level
    `isSidechain`), plus the session total.
    """
    by_model: dict[str, dict] = {}
    by_thread: dict[str, dict] = {}
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
        # Main-loop vs subagent: the native top-level `isSidechain` flag is true
        # on sidechain (subagent) turns. This is the only agent-level signal the
        # harness exposes (#170) — `agent_type`/`agent_id` are never present.
        thread = "subagent" if rec.get("isSidechain") else "main"

        rate = _rate(pricing, model)
        cost = _cost(usage, rate, pricing) if rate else 0.0
        if not rate and model != "unknown":
            unpriced_models.add(model)

        for bucket, key in ((by_model, model), (by_thread, thread)):
            b = bucket.setdefault(key, _new_bucket())
            for f in _TOKEN_FIELDS:
                b[f] += usage.get(f, 0) or 0
            b["cost_usd"] = round(b["cost_usd"] + cost, 6)
            b["messages"] += 1

        for f in _TOKEN_FIELDS:
            totals[f] += usage.get(f, 0) or 0
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
        totals["messages"] += 1

    return {"by_model": by_model, "by_thread": by_thread,
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
    _print_dimension("MODEL", summary["by_model"])
    _print_dimension("THREAD (main/subagent)", summary["by_thread"])
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
        "by_model": _slim(summary["by_model"]),
        "by_thread": _slim(summary["by_thread"]),
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


def _parse_ts(s: str):
    from datetime import datetime, timezone
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def cmd_pace(args, pricing) -> int:
    """Account-level pace: cumulative spend over a rolling window, projected
    against a budget for a billing period; flags when pace would exhaust it."""
    from datetime import datetime, timezone, timedelta
    log = Path(args.log)
    if not log.is_file():
        print("no metrics log yet; nothing to pace")
        return 0
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.window_days)
    in_window = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(e.get("timestamp", ""))
        cost = e.get("total", {}).get("cost_usd", 0.0)
        if ts is not None and ts >= window_start:
            in_window.append((ts, cost))

    spend = round(sum(c for _, c in in_window), 6)
    print(f"# Account pace — last {args.window_days} day(s)")
    print(f"  sessions in window: {len(in_window)}")
    print(f"  cumulative spend:   ${spend:.4f}")
    if not in_window:
        print("  (no sessions in window; nothing to project)")
        return 0

    earliest = min(ts for ts, _ in in_window)
    elapsed_days = max((now - earliest).total_seconds() / 86400.0, 1e-9)
    daily_rate = spend / elapsed_days
    projected = daily_rate * args.period_days
    print(f"  daily rate:         ${daily_rate:.4f}/day "
          f"(over {elapsed_days:.2f} active day(s))")
    print(f"  projected / {args.period_days}d:   ${projected:.4f}")

    if args.budget is not None and args.budget > 0:
        pct = projected / args.budget * 100
        print(f"  budget / {args.period_days}d:       ${args.budget:.2f} "
              f"({pct:.0f}% of budget at current pace)")
        if projected > args.budget:
            print(f"\n⚠ PACE EXCEEDS BUDGET: at ${daily_rate:.4f}/day you would "
                  f"spend ${projected:.2f} over {args.period_days} days, past the "
                  f"${args.budget:.2f} budget.")
            print("  Consider dropping Opus→Sonnet for the remainder of the "
                  "window (see .claude/model-overrides.json / /harness-audit).")
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
    p = sub.add_parser("pace"); p.add_argument("--log", default="metrics/cost-metering.jsonl")
    p.add_argument("--budget", type=float, default=None,
                   help="account budget for one billing period (dollars)")
    p.add_argument("--period-days", type=int, default=30,
                   help="length of the billing period to project against")
    p.add_argument("--window-days", type=int, default=7,
                   help="rolling lookback used to estimate the current daily rate")

    args = ap.parse_args(argv)
    pricing = _load_pricing(Path(args.pricing))
    return {"report": cmd_report, "record": cmd_record,
            "regression": cmd_regression, "pace": cmd_pace}[args.cmd](args, pricing)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
