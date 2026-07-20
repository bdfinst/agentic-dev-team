#!/usr/bin/env python3
"""Run the deferred #1219 live calibration sweep (parallel + resumable).

Issue #1219 is the acceptance step deferred by the combined #1187/#1188 PR:
the model-routing bump (`medium`/`sonnet` -> `claude-sonnet-5`) drifts
`routing_hash()`, marking every calibration record stale, and #1187 shipped
new + rewritten fixtures that need a real floor-clearing run. Both require
live `claude -p` dispatch, so they could not run on a CI merge gate.

This mirrors `scripts/recalibrate_1185.py` (same `agent_calibrate` core,
same record/report writing) with two differences driven by the scale of a
full-universe samples=5 sweep:

1. **Full agent universe**, not a fixed subset — every review agent with a
   floors entry and fixtures gets a fresh record against the new model, so
   `/model-routing-check` reports `calibration-current` for all of them.
2. **Parallel + resumable dispatch.** `agent_calibrate` dispatches
   sequentially through an injected `dispatch_fn`; at ~56s/dispatch a
   ~1875-dispatch samples=5 sweep is ~30h serial. Dispatches are independent
   `claude -p` subprocesses, so this driver runs them through a thread pool
   and memoizes each `(pair, model, sample)` result to an append-only JSONL
   checkpoint. A re-run skips completed cells, so a crash mid-sweep resumes
   instead of restarting. The verdict/record/report logic is still
   `agent_calibrate`'s, fed the memoized majority results via a samples=1
   `dispatch_fn` shim.

Contamination hazard (learned the hard way — the first #1219 run was invalid)
----------------------------------------------------------------------------
A `claude -p /review-agent ...` spawned from *inside* a Claude Code session
inherits the parent's CLAUDE_CODE_SESSION_ID / CLAUDE_CODE_CHILD_SESSION and
can return the parent's narration instead of a fixture review; high
concurrency amplifies this (and proxy 429s) until majority voting papers over
nothing real. Two guards, both in `agent_calibrate` now:
  - `real_dispatch_fn` strips the session-linking vars per subprocess and
    RAISES `DispatchError` on an infra failure (unparseable/`is_error`/narrated
    output) instead of banking it as a false review miss;
  - this driver routes every cell through `dispatch_with_infra_retry` and
    drops a cell to `None` (excluded from the majority) only after retries are
    exhausted — a persistent infra failure is logged, never silently counted.
Even so, prefer a **plain terminal** and **low concurrency**: run this from a
real shell (not nested in an agent session), and keep `--workers` small (the
default is 3, not 12, for this reason).

Run LOCALLY (real proxy access, real tokens/time). Not a cloud gate.

Usage:
    python3 scripts/recalibrate_1219.py                 # full sweep, samples=5
    python3 scripts/recalibrate_1219.py --dry-run        # cost preflight only
    python3 scripts/recalibrate_1219.py --workers 10     # thread-pool width
    python3 scripts/recalibrate_1219.py --agent doc-review --agent a11y-review
    python3 scripts/recalibrate_1219.py --samples 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Belt-and-suspenders session isolation: strip the parent session's linking
# vars from THIS process before any subprocess inherits them. real_dispatch_fn
# also strips per-subprocess, but clearing here means nothing nested — even a
# stray helper — can pick up the parent context (#1219).
for _v in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT"):
    os.environ.pop(_v, None)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import agent_calibrate as ac  # noqa: E402

CHECKPOINT = REPO_ROOT / ".claude" / "evals" / "recalibrate-1219-checkpoint.jsonl"


def eligible_targets(dirs: ac.Dirs, floors: dict) -> list:
    """Every agent-universe target with a floors entry, fixtures, and an agent
    file — i.e. everything a full `--calibrate` sweep will actually dispatch.
    Skills (test-design-advisor) and fixture-less targets (orchestrator) are
    excluded here so the checkpoint/job list only counts real dispatches; the
    reported sweep still runs `calibrate_target` over them and records their
    uncalibratable verdict for completeness."""
    out = []
    for t in ac.target_universe(dirs):
        if t not in floors:
            continue
        if not (dirs.agents / f"{t}.md").is_file():
            continue
        if not ac.fixtures_for_target(t, dirs):
            continue
        out.append(t)
    return out


def load_checkpoint(path: Path) -> dict:
    """(pair, model, sample) -> bool|None for every completed dispatch.
    ``None`` marks a cell that hit a persistent infra failure (excluded from
    the majority, never counted as a review miss)."""
    done = {}
    if not path.exists():
        return done
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ok = rec["ok"]
            done[(rec["pair"], rec["model"], rec["s"])] = None if ok is None else bool(ok)
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--workers", type=int, default=3,
                    help="thread-pool width (default 3). Keep small: high "
                    "concurrency multiplies proxy 429s and nested-session "
                    "contamination into fake flap/floor-failures (#1219).")
    ap.add_argument("--agent", action="append", dest="agents",
                    help="limit to these targets (repeatable); default: full eligible universe")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    dirs = ac.Dirs(REPO_ROOT)
    routing_path = dirs.knowledge / "model-routing.json"
    ladder_path = REPO_ROOT / ".claude" / "model-ladder.json"
    cache_path = REPO_ROOT / "evals" / ".eval-cache.json"
    records_path = REPO_ROOT / ".claude" / "evals" / "calibration-records.json"
    reports_dir = REPO_ROOT / ".claude" / "evals" / "reports"

    floors = ac.load_floors(dirs.knowledge / "calibration-floors.json")
    quarantined = ac.load_quarantine(REPO_ROOT / "memory" / "eval-variance.json")

    targets = args.agents or eligible_targets(dirs, floors)

    band_model = {b: ac.resolve_band(b, routing_path=routing_path,
                                     ladder_path=ladder_path if ladder_path.exists() else None)
                  for b in ac.BANDS}

    # Flat job list: one (pair, model, sample) per real dispatch.
    jobs = []
    for t in targets:
        for pair in ac.fixtures_for_target(t, dirs):
            if pair in quarantined:
                continue
            for band in ac.BANDS:
                model = band_model[band]
                for s in range(args.samples):
                    jobs.append((pair, model, s))

    print(f"targets: {len(targets)}  bands: {band_model}")
    print(f"samples={args.samples}  total dispatch cells: {len(jobs)}")

    done = load_checkpoint(CHECKPOINT)
    todo = [j for j in jobs if (j[0], j[1], j[2]) not in done]
    print(f"checkpoint: {len(done)} done, {len(todo)} remaining")

    if args.dry_run:
        print("--dry-run: stopping before dispatch")
        return 0

    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    completed = [0]

    def run_cell(job):
        pair, model, s = job
        try:
            ok = ac.dispatch_with_infra_retry(pair, model, dirs)
        except ac.DispatchError as exc:
            # Retries exhausted — this cell is an infra failure, NOT a review
            # miss. Record None so aggregation excludes it from the majority
            # denominator instead of banking a false negative (#1219).
            ok = None
            with lock:
                print(f"  INFRA-FAIL {pair} @ {model} s{s}: {exc}", flush=True)
        return job, ok

    fh = CHECKPOINT.open("a")
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_cell, j): j for j in todo}
            for fut in as_completed(futs):
                job, ok = fut.result()
                pair, model, s = job
                done[(pair, model, s)] = ok
                with lock:
                    fh.write(json.dumps({"pair": pair, "model": model, "s": s, "ok": ok}) + "\n")
                    fh.flush()
                    completed[0] += 1
                    n = completed[0]
                    if n % 25 == 0 or n == len(todo):
                        print(f"  [{n}/{len(todo)}] {pair} @ {model} s{s} -> {ok}", flush=True)
    finally:
        fh.close()

    # Aggregate memoized results into a majority verdict per (pair, model),
    # tracking flapping (samples split) exactly as make_pass_rate_fn would.
    majority = {}
    flapped = set()
    model_set = set(band_model.values())
    all_pairs = set()
    for t in targets:
        all_pairs.update(ac.fixtures_for_target(t, dirs))
    for pair in all_pairs:
        for model in model_set:
            # Exclude infra-failed cells (value None) from the denominator —
            # they are not verdicts. Majority is over successful dispatches only.
            valid = [done[(pair, model, s)] for s in range(args.samples)
                     if (pair, model, s) in done and done[(pair, model, s)] is not None]
            if not valid:
                continue
            hits = sum(1 for v in valid if v)
            cells = len(valid)
            if 0 < hits < cells:
                flapped.add(pair)
            majority[(pair, model)] = hits * 2 > cells

    dispatch_fn = lambda pair, model: majority.get((pair, model), False)  # noqa: E731
    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn, samples=1)

    results = []
    for t in targets:
        results.append(ac.calibrate_target(t, dirs, floors, quarantined, pass_rate_fn,
                                            routing_path, ladder_path))

    rhash = ac.routing_hash(routing_path, ladder_path if ladder_path.exists() else None)
    records = ac.load_records(records_path)
    for r in results:
        if r["verdict"] != "uncalibratable":
            records[r["target"]] = ac.build_record(r, rhash)
    ac.save_records(records_path, records)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    net = len(jobs)
    report = ac.render_report(results, ts, (net, 0, net), sorted(flapped))
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{ts}-calibration-1219.md"
    report_path.write_text(report)

    print(f"\nrecords: {records_path}")
    print(f"report:  {report_path}")
    for r in results:
        print(f"  {r['target']}: {r['verdict']} "
              f"(declared={r['declared_band']} calibrated={r['calibrated_band']})")
    if flapped:
        print(f"\nFLAPPING ({len(flapped)}):")
        for p in sorted(flapped):
            print(f"  {p}")
    else:
        print("\nno flapping fixtures (all samples decisive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
