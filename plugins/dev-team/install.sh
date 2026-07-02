#!/usr/bin/env bash
# install.sh — thin trampoline that hands off to install.py.
#
# Per ADR 0014, new shipped scripts are Python; this file remains as a
# .sh only to preserve the well-known `install.sh` command surface AND
# to detect the shell environment (Git Bash on Windows) before Python
# is guaranteed on PATH.
#
# Behavior:
#   - If `python3` is on PATH, delegate to install.py (which does the
#     actual prerequisite check).
#   - Otherwise, fail loudly with an install pointer.
#
# Usage:
#   ./install.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] python3 — required. Install Python 3.8+."
  echo "  macOS: brew install python3"
  echo "  Linux: apt install python3 (or your distro's equivalent)"
  echo "  Windows: install Git Bash + Python 3 from python.org"
  exit 1
fi

exec python3 "$SCRIPT_DIR/install.py" "$@"
