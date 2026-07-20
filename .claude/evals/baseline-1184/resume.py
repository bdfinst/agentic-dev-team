#!/usr/bin/env python3
"""Resume the #1184 calibration baseline on a local machine, from the exact cell
where the cloud session froze it.

The driver (run_baseline_1184.py) is per-sample checkpointed and restart-durable:
it reads .claude/evals/baseline-1184/{cells,samples}.json, runs only the
cells/samples not yet banked, and — once all 360 cells are done — writes
verdicts.json and .claude/evals/calibration-records.json, then prints the verdict
table followed by "DONE".

Usage (from anywhere inside the repo, after `git pull`):

    python3 .claude/evals/baseline-1184/resume.py

Prereqs on this machine:
  - an authenticated `claude` CLI: the driver samples the model through the same
    dispatch the plugin uses, so model access must work locally.

Files arrive already in their correct locations via `git pull` — this script
verifies them and launches; it does not need to relocate anything.

Python (not bash) per ADR 0014 (docs/adr/0014-python-for-cross-os-scripts.md):
new scripts in this repo are stdlib-only Python.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DRIVER_REL = Path(".claude/evals/baseline-1184/run_baseline_1184.py")
CKPT_REL = Path(".claude/evals/baseline-1184/cells.json")


def repo_root() -> Path:
    """Prefer git (works from any subdir); fall back to $HOME/_git/agentic-dev-team
    (where the local clone lives)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except OSError:
        pass
    return Path(os.path.expanduser("~/_git/agentic-dev-team"))


def main() -> int:
    root = repo_root()
    os.chdir(root)

    if not (root / "scripts" / "agent_calibrate.py").is_file():
        sys.exit("ERROR: scripts/agent_calibrate.py missing — is this the repo "
                 "root, on branch claude/setup-0dkgat?")
    if not DRIVER_REL.is_file():
        sys.exit(f"ERROR: driver missing at {DRIVER_REL} — did the branch pull "
                 "cleanly?")

    banked = 0
    if CKPT_REL.is_file():
        try:
            banked = len(json.loads(CKPT_REL.read_text()))
        except (OSError, json.JSONDecodeError):
            banked = 0

    print(f"Repo:     {root}")
    print(f"Resuming: {banked}/360 cells already banked; the driver runs only "
          "what's left.")
    print("Mode:     foreground — the #1184 verdict table prints on completion "
          "(DONE).")
    print()

    # Hand off to the driver. PYTHONPATH is belt-and-suspenders — the driver also
    # inserts "scripts" onto sys.path itself.
    env = dict(os.environ, PYTHONPATH="scripts")
    os.execvpe(sys.executable, [sys.executable, str(DRIVER_REL)], env)


if __name__ == "__main__":
    raise SystemExit(main())
