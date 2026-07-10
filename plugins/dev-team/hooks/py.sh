#!/bin/sh
# py.sh — resolve a working Python 3 interpreter and exec it with the given args.
#
# Ships as .sh (not .py) by necessity: it runs BEFORE a Python interpreter is
# guaranteed on PATH, so it cannot itself be Python. This is the same
# pre-Python bootstrap carve-out ADR 0015 grants install.sh — not a regression
# on the "shipped scripts are Python" rule.
#
# Why it exists: every hook command in settings.json and the /version skill
# route their Python invocations through this shim so the plugin works on
# machines where Python 3 exists under a name other than `python3`. Notably
# Windows, where python.org installs `python.exe`/`py.exe` but NOT
# `python3.exe`, and the only `python3` on PATH is the WindowsApps
# app-execution-alias stub that refuses to run non-interactively. Many
# locked-down corporate users cannot install packages to fix this themselves
# but do have Python 3 as `python`/`py`.
#
# Resolution order: $DEV_TEAM_PYTHON override, then python3, py -3, python.
# Each candidate is *executed* (not just located with `command -v`) so the
# Store stub and Python 2 are rejected on behavior, not name. The winner is
# cached for the session so only the first call pays the probe cost.
#
# Usage:  sh hooks/py.sh <script.py> [args...]
# Exit 2 (environment error) when no Python 3 is found — matches the hook
# contract's exit-2 semantics.

set -u

# Match version_check.py's cache convention: a bare /tmp literal is portable to
# Windows Git Bash (MSYS mounts it), so no ${TMPDIR:-/tmp} dance is needed.
# $DEV_TEAM_PY_CACHE overrides the path (used by tests for isolation).
CACHE="${DEV_TEAM_PY_CACHE:-/tmp/.dev-team-python}"

# A candidate is valid only if it runs AND reports major version >= 3. All
# output is discarded so the Store stub's "not found" banner never surfaces and
# a candidate that prints nothing is judged purely on exit status.
valid() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$@" -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' \
        >/dev/null 2>&1
}

# Fast path: trust a cached interpreter if its first token still resolves.
# Skipped when DEV_TEAM_PYTHON is set so an explicit override always wins over a
# stale cache.
if [ -z "${DEV_TEAM_PYTHON:-}" ] && [ -f "$CACHE" ]; then
    read -r PY <"$CACHE" 2>/dev/null || PY=""
    if [ -n "$PY" ] && command -v "${PY%% *}" >/dev/null 2>&1; then
        exec $PY "$@"
    fi
fi

PY=""
# Intentional word-split: DEV_TEAM_PYTHON may be a multi-word command like "py -3".
# shellcheck disable=SC2086
if [ -n "${DEV_TEAM_PYTHON:-}" ] && valid ${DEV_TEAM_PYTHON}; then
    PY="${DEV_TEAM_PYTHON}"
elif valid python3; then
    PY="python3"
elif valid py -3; then
    PY="py -3"
elif valid python; then
    PY="python"
else
    echo "dev-team: no Python 3 interpreter found (tried \$DEV_TEAM_PYTHON, python3, py -3, python)." >&2
    echo "dev-team: install Python 3.8+ or set DEV_TEAM_PYTHON to a working interpreter." >&2
    exit 2
fi

# Best-effort cache; a read-only /tmp is non-fatal.
printf '%s\n' "$PY" >"$CACHE" 2>/dev/null || true

exec $PY "$@"
