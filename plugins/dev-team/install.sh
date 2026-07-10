#!/usr/bin/env bash
# install.sh — thin trampoline that resolves a Python 3 interpreter and hands
# off to install.py.
#
# Per ADR 0014, new shipped scripts are Python; this file remains a .sh only to
# preserve the well-known `install.sh` command surface AND to bootstrap before
# Python is guaranteed on PATH.
#
# Interpreter resolution is delegated to the shared hooks/py.sh shim, which
# tries $DEV_TEAM_PYTHON, python3, py -3, then python — so install works on
# Windows, where Python 3 is commonly `python`/`py` and no `python3` exists.
# py.sh prints an actionable message and exits 2 when no Python 3 is found.
#
# Usage:
#   ./install.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec sh "$SCRIPT_DIR/hooks/py.sh" "$SCRIPT_DIR/install.py" "$@"
