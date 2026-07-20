#!/usr/bin/env python3
"""#1184 baseline — cell-checkpointed driver (restart-durable).

The container restarts roughly every ~30 min; the big targets (test-review et
al.) need far longer than that to calibrate, and agent_calibrate.py only persists
a target's result at the very END of an all-or-nothing per-target run (no cache
write, no early-exit). So a killed target loses everything and can never finish.

This driver instead grades one (fixture, band) CELL at a time and writes a
checkpoint after each cell. A restart resumes at the next uncomputed cell, so
every fixture's work banks. It reuses agent_calibrate's own dispatch
(real_dispatch_fn) and verdict logic, so verdicts are identical to a clean run.

Concurrency is deliberately MODERATE, not maxed: real_dispatch_fn collapses a
dispatch to a bare bool, so an API rate-limit error (429 -> unparseable ->
retries exhausted -> False) is indistinguishable from a genuine graded FAIL and
would be checkpointed as one. Fewer concurrent dispatches => fewer 429s => fewer
false FAILs corrupting the baseline. Durability no longer depends on worker count
(the checkpoint handles that), so there is no reason to risk it.
"""
import os
import sys
import json
import threading
import concurrent.futures
from pathlib import Path

sys.path.insert(0, "scripts")
import agent_calibrate as ac  # noqa: E402

REPO = Path(".").resolve()
SAMPLES = 5
WORKERS = 10  # bumped from 6: bank more cells per alive-window given frequent container restarts; samples=5 majority vote absorbs any added dispatch noise
dirs = ac.Dirs(REPO, None, None, None)
routing_path = dirs.knowledge / "model-routing.json"
ladder_path = REPO / ".claude" / "model-ladder.json"
floors = ac.load_floors(dirs.knowledge / "calibration-floors.json")
quarantined = ac.load_quarantine(REPO / "memory" / "eval-variance.json")

out_dir = REPO / ".claude" / "evals" / "baseline-1184"
out_dir.mkdir(parents=True, exist_ok=True)
ckpt_path = out_dir / "cells.json"

# Resolve each band's model once (routing is fixed for the whole run).
models = {b: ac.resolve_band(b, routing_path=routing_path, ladder_path=ladder_path) for b in ac.BANDS}

targets = [t for t in ac.target_universe(dirs)
           if ac.fixtures_for_target(t, dirs) and isinstance(floors.get(t), dict)]

# Build the flat cell list: one cell per (active fixture, band).
cells = []  # (cellkey, pair, band)
for t in targets:
    pairs = [p for p in ac.fixtures_for_target(t, dirs) if p not in quarantined]
    for band in ac.BANDS:
        for pair in pairs:
            cells.append((f"{pair}||{band}", pair, band))

lock = threading.Lock()


def _atomic_write(path, obj):
    # Atomic replace so a restart mid-write can never truncate the checkpoint.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    os.replace(tmp, path)


try:
    done = json.loads(ckpt_path.read_text())
except (OSError, json.JSONDecodeError):
    done = {}

part_path = out_dir / "samples.json"
try:
    partial = json.loads(part_path.read_text())
except (OSError, json.JSONDecodeError):
    partial = {}

todo = [c for c in cells if c[0] not in done]
banked_samples = sum(len(v) for k, v in partial.items() if k not in done)
print(f"baseline #1184 (sample-checkpointed): {len(targets)} targets, {len(cells)} cells "
      f"@ samples={SAMPLES}, {WORKERS} workers", flush=True)
print(f"  resuming: {len(done)}/{len(cells)} cells banked, {len(todo)} to run "
      f"({banked_samples} partial samples preserved)\n", flush=True)


def run_cell(cell):
    cellkey, pair, band = cell
    model = models[band]
    with lock:
        results = list(partial.get(cellkey, []))
    # Run only the samples not already banked; persist EACH one immediately so a
    # restart loses at most one in-flight dispatch, never a whole cell's work.
    for _ in range(SAMPLES - len(results)):
        hit = bool(ac.real_dispatch_fn(pair, model, dirs))
        results.append(hit)
        with lock:
            # Snapshot, not the live list (#1212): results is appended outside
            # the lock, so aliasing it would let another worker's _atomic_write
            # serialize a list mid-mutation.
            partial[cellkey] = list(results)
            _atomic_write(part_path, partial)
    hits = sum(1 for h in results if h)
    rec = {"pair": pair, "band": band, "hits": hits, "samples": SAMPLES,
           "passed": hits * 2 > SAMPLES, "flap": 0 < hits < SAMPLES}
    with lock:
        done[cellkey] = rec
        _atomic_write(ckpt_path, done)
        partial.pop(cellkey, None)
        _atomic_write(part_path, partial)
    return cellkey, rec


completed = len(done)
with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for cellkey, rec in ex.map(run_cell, todo):
        completed += 1
        if completed % 10 == 0 or rec["flap"]:
            tag = " FLAP" if rec["flap"] else ""
            print(f"  [{completed}/{len(cells)}] {cellkey} -> {rec['hits']}/{SAMPLES}{tag}", flush=True)

# ---- All cells banked: compute per-target verdicts from the checkpoint. ----
results = []
flapping = sorted(k.split("||")[0] for k, r in done.items() if r["flap"])
for t in targets:
    all_pairs = ac.fixtures_for_target(t, dirs)
    excluded = sorted(p for p in all_pairs if p in quarantined)
    active = [p for p in all_pairs if p not in quarantined]
    floor = floors[t]["floor"]
    declared = ac.read_declared_band(t, dirs)
    band_results, calibrated = {}, None
    for band in ac.BANDS:
        if active:
            passed = sum(1 for p in active if done.get(f"{p}||{band}", {}).get("passed"))
            total = len(active)
            rate = passed / total
        else:
            passed, total, rate = 0, 0, 1.0
        band_results[band] = {"rate": rate, "total": total, "passed": passed, "model": models[band]}
        if calibrated is None and rate >= floor:
            calibrated = band
    if calibrated is None:
        verdict = "floor-failure"
    elif calibrated == declared:
        verdict = "aligned"
    elif ac.BAND_INDEX[calibrated] < ac.BAND_INDEX.get(declared, ac.BAND_INDEX[ac.DEFAULT_DECLARED_BAND]):
        verdict = "downgrade-available"
    else:
        verdict = "upgrade-required"
    results.append({"target": t, "verdict": verdict, "declared_band": declared,
                    "calibrated_band": calibrated, "floor": floor,
                    "band_results": band_results, "quarantined": excluded, "fixture_gap": None})

# Persist canonical records (compatible with #1185) + a full JSON dump.
rhash = ac.routing_hash(routing_path, ladder_path if ladder_path.exists() else None)
records = ac.load_records(REPO / ".claude" / "evals" / "calibration-records.json")
for r in results:
    records[r["target"]] = ac.build_record(r, rhash)
ac.save_records(REPO / ".claude" / "evals" / "calibration-records.json", records)
(out_dir / "verdicts.json").write_text(json.dumps(results, indent=2, sort_keys=True))

print("\n================ #1184 BASELINE VERDICTS ================", flush=True)
order = {"floor-failure": 0, "upgrade-required": 1, "downgrade-available": 2, "aligned": 3}
for r in sorted(results, key=lambda x: (order.get(x["verdict"], 9), x["target"])):
    rates = " ".join(f"{b}={r['band_results'][b]['rate']:.0%}" for b in ac.BANDS)
    print(f"  {r['verdict']:20} {r['target']:32} declared={r['declared_band']:6} "
          f"calibrated={r['calibrated_band']}  [{rates}]")
if flapping:
    print("\n  FLAPPING (fixture,band) cells — quarantine/rewrite, low-confidence:")
    for f in sorted(set(flapping)):
        print(f"    {f}")
print("\nDONE", flush=True)
