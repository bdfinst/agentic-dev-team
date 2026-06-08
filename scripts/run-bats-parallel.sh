#!/usr/bin/env bash
# run-bats-parallel.sh — run bats suites across files concurrently using only
# POSIX-ubiquitous tooling, so no GNU `parallel` install is required on dev
# machines or CI.
#
# Why not `bats --jobs`: that flag needs GNU `parallel` on PATH (a Homebrew /
# apt package not present by default on macOS). `xargs -P` ships with both
# macOS (BSD xargs) and Linux (GNU xargs) out of the box, so this runner is
# portable everywhere with nothing to install. Safe on stock macOS bash 3.2.
#
# Usage:
#   run-bats-parallel.sh [-j JOBS] <file-or-dir>...
#
# Directories are expanded to their *.bats files; bare files pass through.
# Each .bats file runs in its own bats process; up to JOBS run concurrently
# (default: online core count). Every file runs even if others fail — the
# exit code is non-zero iff ANY file failed (collect-all-failures, matching
# the serial runner's contract).

set -uo pipefail

JOBS=""
while [ "${1:-}" = "-j" ]; do
  JOBS="${2:-}"
  shift 2
done

if [ -z "$JOBS" ]; then
  JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
fi
case "$JOBS" in '' | *[!0-9]*) JOBS=2 ;; esac
[ "$JOBS" -ge 1 ] || JOBS=2

# Collect .bats files: directories expand to their *.bats (sorted for a stable
# run order), bare paths pass through unchanged.
files=()
for p in "$@"; do
  if [ -d "$p" ]; then
    while IFS= read -r f; do
      files+=("$f")
    done < <(find "$p" -type f -name '*.bats' | sort)
  elif [ -n "$p" ]; then
    files+=("$p")
  fi
done

if [ "${#files[@]}" -eq 0 ]; then
  echo "run-bats-parallel: no .bats files found in: $*" >&2
  exit 0
fi

# Fan the files across up to JOBS bats processes. xargs -P (parallel) and -0
# (NUL-delimited, space-safe) are supported by both BSD and GNU xargs. bats
# exits 1 on a test failure (not 255), so xargs keeps launching the rest and
# then reports non-zero overall — exactly the collect-all-failures behavior we
# want for a pre-push gate.
printf '%s\0' "${files[@]}" | xargs -0 -P "$JOBS" -n1 bats
