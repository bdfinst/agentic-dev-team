#!/usr/bin/env bash
#
# Resume the #1184 calibration baseline on a local machine, from the exact cell
# where the cloud session froze it.
#
# The driver (run_baseline_1184.py) is per-sample checkpointed and
# restart-durable: it reads .claude/evals/baseline-1184/{cells,samples}.json,
# runs only the cells/samples not yet banked, and — once all 360 cells are done —
# writes verdicts.json and .claude/evals/calibration-records.json, then prints the
# verdict table followed by "DONE".
#
# Usage (from anywhere inside the repo, after `git pull`):
#     bash .claude/evals/baseline-1184/resume.sh
#
# Prereqs on this machine:
#   - python3 on PATH
#   - an authenticated `claude` CLI: the driver samples the model through the
#     same dispatch the plugin uses, so model access must work locally.
#
# Files arrive already in their correct locations via `git pull` — this script
# verifies them and launches; it does not need to relocate anything.

set -euo pipefail

# Locate the repo root: prefer git (works from any subdir), else $HOME fallback.
if REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    :
else
    REPO="$HOME/agentic-dev-team"
fi
cd "$REPO"

DRIVER=".claude/evals/baseline-1184/run_baseline_1184.py"
CKPT=".claude/evals/baseline-1184/cells.json"

# --- Preflight: fail early with an actionable message rather than mid-run. ---
command -v python3 >/dev/null 2>&1 \
    || { echo "ERROR: python3 not found on PATH." >&2; exit 1; }
[ -f "scripts/agent_calibrate.py" ] \
    || { echo "ERROR: scripts/agent_calibrate.py missing — is this the repo root, on branch claude/setup-0dkgat?" >&2; exit 1; }
[ -f "$DRIVER" ] \
    || { echo "ERROR: driver missing at $DRIVER — did the branch pull cleanly?" >&2; exit 1; }

banked="$(python3 -c "import json,os; p='$CKPT'; print(len(json.load(open(p))) if os.path.exists(p) else 0)")"

echo "Repo:     $REPO"
echo "Resuming: ${banked}/360 cells already banked; the driver runs only what's left."
echo "Mode:     foreground — the #1184 verdict table prints on completion (DONE)."
echo "          (To background it instead: nohup bash $0 >resume.log 2>&1 &)"
echo

# Hand off to the driver. PYTHONPATH is belt-and-suspenders — the driver also
# inserts "scripts" onto sys.path itself.
exec env PYTHONPATH=scripts python3 "$DRIVER"
