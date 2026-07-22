#!/usr/bin/env python3
"""CLI supervisor for a restart-durable eval.

Wraps ``durable_runner`` with the three operations a long cloud-session eval
needs, so none of them has to be re-invented per eval:

    run           launch the durable run in the foreground
    status        print checkpoint progress without touching the run
    ensure-alive  relaunch the run (detached) iff no live driver owns this
                  out-dir and it is not already DONE — the guard-relaunch
                  primitive the supervision loop and the backstop both call

An *eval module* is an ordinary Python file that supplies only the
eval-specific bits:

    cells() -> list[(key, payload)]     # or a module-level CELLS list
    sample(payload) -> json-serializable
    reduce(samples, key, payload) -> dict     # optional
    finalize(done, out_dir) -> summary        # optional
    SAMPLES, WORKERS                          # optional int defaults
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import durable_runner


def _load_module(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import eval module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cells(mod):
    if hasattr(mod, "cells"):
        return list(mod.cells())
    if hasattr(mod, "CELLS"):
        return list(mod.CELLS)
    raise SystemExit("eval module must define cells() or CELLS")


def _run(args):
    mod = _load_module(args.module)
    samples = args.samples if args.samples is not None else getattr(mod, "SAMPLES", 5)
    workers = args.workers if args.workers is not None else getattr(mod, "WORKERS", 10)
    durable_runner.run_durable(
        _cells(mod),
        mod.sample,
        args.out,
        samples=samples,
        workers=workers,
        reduce=getattr(mod, "reduce", None),
        finalize=getattr(mod, "finalize", None),
        flag=getattr(mod, "flag", None),
    )


def _status(args):
    st = durable_runner.status(args.out)
    if args.json:
        print(json.dumps(st))
    else:
        print(
            f"banked {st['banked']} | partial-samples {st['partial_samples']} "
            f"| DONE={st['done']} | summary={st['has_summary']}"
        )
    return st


def _live_pid(out_dir):
    """PID of a running `run_eval.py run --out <out_dir>`, or None."""
    marker = str(Path(out_dir).resolve())
    try:
        ps = subprocess.run(
            ["ps", "-eo", "pid,args"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    self_pid = str(subprocess.os.getpid())
    for line in ps.splitlines()[1:]:
        pid, _, cmd = line.strip().partition(" ")
        if pid == self_pid:
            continue
        if "run_eval.py" in cmd and " run" in cmd and marker in cmd:
            return pid
    return None


def _ensure_alive(args):
    out_dir = Path(args.out).resolve()
    if (out_dir / "DONE").exists():
        print("DONE — not relaunching")
        return
    pid = _live_pid(out_dir)
    if pid:
        print(f"live (pid {pid})")
        _status(args)
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    log = open(out_dir / "driver.log", "ab")
    cmd = [
        sys.executable, str(Path(__file__).resolve()), "run",
        "--module", str(Path(args.module).resolve()),
        "--out", str(out_dir),
    ]
    if args.samples is not None:
        cmd += ["--samples", str(args.samples)]
    if args.workers is not None:
        cmd += ["--workers", str(args.workers)]
    # start_new_session detaches the child so it outlives this short-lived
    # supervisor call (and is only killed by the next container recycle).
    subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True, close_fds=True)
    print("RELAUNCHED (was dead)")
    _status(args)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="launch the durable run (foreground)")
    pr.add_argument("--module", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--samples", type=int, default=None)
    pr.add_argument("--workers", type=int, default=None)
    pr.set_defaults(fn=_run)

    ps = sub.add_parser("status", help="print checkpoint progress")
    ps.add_argument("--out", required=True)
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(fn=_status)

    pe = sub.add_parser("ensure-alive", help="relaunch (detached) iff dead and not DONE")
    pe.add_argument("--module", required=True)
    pe.add_argument("--out", required=True)
    pe.add_argument("--samples", type=int, default=None)
    pe.add_argument("--workers", type=int, default=None)
    pe.add_argument("--json", action="store_true")
    pe.set_defaults(fn=_ensure_alive)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
