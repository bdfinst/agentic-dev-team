#!/usr/bin/env python3
"""Worked eval module: agent model-band calibration, made restart-durable.

Copy this shape for your own long eval. It plugs the repo's ``agent_calibrate``
dispatch/verdict logic into ``durable_runner`` via the module contract that
``run_eval.py`` expects:

    cells()  -> one cell per (active fixture, band)
    sample() -> one real dispatch, collapsed to a pass/fail bool
    reduce() -> majority-vote record for a cell (+ flap flag)
    finalize() -> per-target verdicts written to summary.json

Run it durably (from the repo root) with:

    python3 ${CLAUDE_PLUGIN_ROOT}/skills/long-eval/run_eval.py ensure-alive \\
        --module ${CLAUDE_PLUGIN_ROOT}/skills/long-eval/example_calibration.py \\
        --out .claude/evals/calibration

The pure helpers (``reduce``, ``flag``) import nothing heavy, so they are unit
tested directly; ``cells``/``sample``/``finalize`` need the live repo and are
exercised by the real run, not by unit tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

SAMPLES = 5
WORKERS = 10

_REPO = Path(".").resolve()


def _ac():
    """Import the repo's calibration module lazily (keeps plain import cheap)."""
    sys.path.insert(0, str(_REPO / "scripts"))
    import agent_calibrate as ac  # noqa: E402

    return ac


def _dirs(ac):
    return ac.Dirs(_REPO, None, None, None)


def _models(ac, dirs):
    routing = dirs.knowledge / "model-routing.json"
    ladder = _REPO / ".claude" / "model-ladder.json"
    return {b: ac.resolve_band(b, routing_path=routing, ladder_path=ladder) for b in ac.BANDS}


def cells():
    ac = _ac()
    dirs = _dirs(ac)
    floors = ac.load_floors(dirs.knowledge / "calibration-floors.json")
    quarantined = ac.load_quarantine(_REPO / "memory" / "eval-variance.json")
    models = _models(ac, dirs)
    targets = [
        t for t in ac.target_universe(dirs)
        if ac.fixtures_for_target(t, dirs) and isinstance(floors.get(t), dict)
    ]
    out = []
    for t in targets:
        pairs = [p for p in ac.fixtures_for_target(t, dirs) if p not in quarantined]
        for band in ac.BANDS:
            for pair in pairs:
                out.append((f"{pair}||{band}", (pair, band, models[band])))
    return out


def sample(payload):
    """One real dispatch, collapsed to a pass/fail bool (majority-voted later)."""
    ac = _ac()
    pair, _band, model = payload
    return bool(ac.real_dispatch_fn(pair, model, _dirs(ac)))


def reduce(samples, key, payload):
    pair, band, _model = payload
    hits = sum(1 for h in samples if h)
    n = len(samples)
    return {
        "pair": pair, "band": band, "hits": hits, "samples": n,
        "passed": hits * 2 > n, "flap": 0 < hits < n,
    }


def flag(record):
    return bool(record.get("flap"))


def finalize(done, out_dir):
    ac = _ac()
    dirs = _dirs(ac)
    floors = ac.load_floors(dirs.knowledge / "calibration-floors.json")
    quarantined = ac.load_quarantine(_REPO / "memory" / "eval-variance.json")
    models = _models(ac, dirs)
    targets = [
        t for t in ac.target_universe(dirs)
        if ac.fixtures_for_target(t, dirs) and isinstance(floors.get(t), dict)
    ]
    results = []
    for t in targets:
        active = [p for p in ac.fixtures_for_target(t, dirs) if p not in quarantined]
        floor = floors[t]["floor"]
        declared = ac.read_declared_band(t, dirs)
        band_results, calibrated = {}, None
        for band in ac.BANDS:
            passed = sum(1 for p in active if done.get(f"{p}||{band}", {}).get("passed"))
            rate = passed / len(active) if active else 1.0
            band_results[band] = {"rate": rate, "passed": passed, "total": len(active)}
            if calibrated is None and rate >= floor:
                calibrated = band
        if calibrated is None:
            verdict = "floor-failure"
        elif calibrated == declared:
            verdict = "aligned"
        elif ac.BAND_INDEX[calibrated] < ac.BAND_INDEX.get(
            declared, ac.BAND_INDEX[ac.DEFAULT_DECLARED_BAND]
        ):
            verdict = "downgrade-available"
        else:
            verdict = "upgrade-required"
        results.append({
            "target": t, "verdict": verdict, "declared_band": declared,
            "calibrated_band": calibrated, "floor": floor, "band_results": band_results,
        })
    return results
