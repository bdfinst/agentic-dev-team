#!/usr/bin/env python3
"""Restart-durable eval engine.

Cloud sessions run in a container that is recycled on a short cadence (often
every few minutes). A recycle kills every in-container process but *keeps the
working tree* — checkpoints written to disk survive, running processes do not.
Any eval longer than one container lifetime must therefore checkpoint its work
so a relaunch resumes instead of restarting from zero.

This engine grades one **cell** (an independent unit of work) at a time and
writes a checkpoint after every cell — and, within a cell, after every sample.
A relaunch resumes at the next unbanked sample, so at most one in-flight
dispatch is ever lost. It is deliberately eval-agnostic: callers supply the
cell list and a `sample` function; calibration, prompt A/B tests, and
judge-panel runs all reuse the same durable core.

Layout under `out_dir`:
    cells.json    completed cell records            {key: record}
    samples.json  partial per-cell sample lists      {key: [sample, ...]}
    summary.json  finalize() output (once complete)  (optional)
    DONE          sentinel written when all cells are banked + finalized

Concurrency is intentionally moderate. When `sample` collapses a rich outcome
to a bare bool (e.g. "did the agent pass"), a transport error is
indistinguishable from a genuine negative and would be checkpointed as one.
Fewer concurrent dispatches means fewer such errors; durability comes from the
checkpoint, not from a large worker pool, so there is no reason to max it out.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import threading
from pathlib import Path


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write(path: Path, obj) -> None:
    """Replace `path` atomically so a recycle mid-write can never truncate it."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _default_reduce(samples, key, payload):
    return {"samples": samples, "n": len(samples)}


def run_durable(
    cells,
    sample,
    out_dir,
    *,
    samples=5,
    workers=10,
    reduce=None,
    finalize=None,
    progress_every=10,
    flag=None,
    logger=print,
):
    """Run a checkpointed, restart-durable eval.

    Args:
        cells: iterable of ``(key, payload)``. ``key`` must be a stable JSON
            string that is identical across relaunches (it is the checkpoint
            identity); ``payload`` is any object passed straight to ``sample``
            and is never persisted — the caller reconstructs it each launch.
        sample: ``callable(payload) -> json-serializable``. One independent
            trial. Called up to ``samples`` times per cell.
        out_dir: directory for the checkpoint files (created if absent).
        samples: trials per cell.
        workers: thread-pool size.
        reduce: ``callable(samples_list, key, payload) -> dict`` producing the
            cell record. Defaults to ``{"samples": [...], "n": len}``.
        finalize: ``callable(done_records, out_dir) -> summary`` run once, only
            when every cell is banked. Its return value is written to
            ``summary.json`` and a ``DONE`` sentinel is created.
        progress_every: emit a progress line every N completed cells.
        flag: ``callable(record) -> bool``; when true, force a progress line for
            that cell regardless of ``progress_every`` (e.g. flagging a flap).
        logger: line sink (defaults to ``print``).

    Returns:
        ``(done, summary)`` — the full ``{key: record}`` map and the finalize
        return value (``None`` if the run is not yet complete or has no
        finalize).
    """
    reduce = reduce or _default_reduce
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cells_path = out_dir / "cells.json"
    samples_path = out_dir / "samples.json"

    cells = list(cells)
    done = _load_json(cells_path, {})
    partial = _load_json(samples_path, {})
    lock = threading.Lock()

    todo = [(k, p) for (k, p) in cells if k not in done]
    banked = sum(len(v) for k, v in partial.items() if k not in done)
    logger(
        f"durable run: {len(cells)} cells @ samples={samples}, {workers} workers"
    )
    logger(
        f"  resuming: {len(done)}/{len(cells)} banked, {len(todo)} to run "
        f"({banked} partial samples preserved)"
    )

    def run_cell(cell):
        key, payload = cell
        with lock:
            results = list(partial.get(key, []))
        # Only run the samples not already banked; persist EACH immediately so a
        # recycle loses at most one in-flight dispatch, never a whole cell.
        for _ in range(samples - len(results)):
            results.append(sample(payload))
            with lock:
                # Snapshot, not the live list: `results` is appended outside the
                # lock, so aliasing it into `partial` would let another worker's
                # _atomic_write serialize a list mid-mutation (#1212).
                partial[key] = list(results)
                _atomic_write(samples_path, partial)
        record = reduce(results, key, payload)
        with lock:
            done[key] = record
            _atomic_write(cells_path, done)
            partial.pop(key, None)
            _atomic_write(samples_path, partial)
        return key, record

    completed = len(done)
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(run_cell, c) for c in todo]
        for fut in concurrent.futures.as_completed(futures):
            try:
                key, record = fut.result()
            except Exception as exc:  # noqa: BLE001 — one poison cell must not
                failures += 1        # kill the pool; it stays unbanked for the
                logger(f"  ERROR cell failed, will retry next launch: {exc!r}")
                continue
            completed += 1
            if completed % progress_every == 0 or (flag and flag(record)):
                marker = " *" if flag and flag(record) else ""
                logger(f"  [{completed}/{len(cells)}] {key}{marker}")

    if len(done) < len(cells):
        logger(
            f"incomplete: {len(done)}/{len(cells)} banked, {failures} errored "
            f"this pass — relaunch to resume"
        )
        return done, None

    summary = finalize(done, out_dir) if finalize else None
    if summary is not None:
        _atomic_write(out_dir / "summary.json", summary)
    (out_dir / "DONE").write_text("")
    logger("DONE")
    return done, summary


def status(out_dir):
    """Return a checkpoint-progress dict for `out_dir` without running anything."""
    out_dir = Path(out_dir)
    done = _load_json(out_dir / "cells.json", {})
    partial = _load_json(out_dir / "samples.json", {})
    return {
        "banked": len(done),
        "partial_cells": sum(1 for k in partial if k not in done),
        "partial_samples": sum(len(v) for k, v in partial.items() if k not in done),
        "done": (out_dir / "DONE").exists(),
        "has_summary": (out_dir / "summary.json").exists(),
    }
