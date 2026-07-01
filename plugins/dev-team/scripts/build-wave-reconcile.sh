#!/usr/bin/env bash
# build-wave-reconcile.sh — serially merge a wave's completed slice branches into
# an integration branch, then gate on the full suite before the next wave.
#
# Order-independent: branches are merged in a deterministic (sorted) order, and
# because same-wave slices touch disjoint files (the parallelization review and
# build-wave.sh guarantee it) the merged tree is identical regardless of the order
# slices finished. If two branches unexpectedly touch the same file, the merge
# conflicts — the script halts LOUDLY (exit 1, names the file) and **picks no
# side** (it aborts the merge), starting no next-wave slice.
#
# Usage:
#   build-wave-reconcile.sh --into <branch> --base <ref> [--test-cmd CMD] <slice-branch>...

set -uo pipefail

INTO=""; BASE=""; TESTCMD=""
branches=()
while [ $# -gt 0 ]; do
  case "$1" in
    --into)     INTO="${2:-}"; shift 2 ;;
    --base)     BASE="${2:-}"; shift 2 ;;
    --test-cmd) TESTCMD="${2:-}"; shift 2 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *)  branches+=("$1"); shift ;;
  esac
done
{ [ -n "$INTO" ] && [ -n "$BASE" ] && [ "${#branches[@]}" -gt 0 ]; } || {
  echo "usage: build-wave-reconcile.sh --into <branch> --base <ref> [--test-cmd CMD] <slice-branch>..." >&2
  exit 2
}

# Deterministic merge order -> reproducible tree regardless of caller order.
sorted=()
while IFS= read -r b; do sorted+=("$b"); done < <(printf '%s\n' "${branches[@]}" | sort)

# If $INTO already exists, reconcile onto its current tip so any commits the
# caller made directly on the integration branch (e.g. spec/plan WIP commits
# made before or between wave dispatches) stay in the ancestry. Only create
# $INTO fresh from $BASE when it does not exist yet — resetting an existing
# $INTO to $BASE would silently discard those WIP commits.
if git rev-parse --verify --quiet "$INTO" >/dev/null 2>&1; then
  git checkout "$INTO" >/dev/null 2>&1 || {
    echo "build-wave-reconcile: cannot check out existing integration branch '$INTO'." >&2
    exit 2
  }
else
  git checkout -B "$INTO" "$BASE" >/dev/null 2>&1 || {
    echo "build-wave-reconcile: cannot create integration branch '$INTO' from '$BASE'." >&2
    exit 2
  }
fi

for b in "${sorted[@]}"; do
  if ! git merge --no-ff --no-edit "$b" >/dev/null 2>&1; then
    conflicted="$(git diff --name-only --diff-filter=U | paste -sd', ' -)"
    git merge --abort >/dev/null 2>&1 || true
    echo "build-wave-reconcile: CONFLICT — same-wave branches touch '${conflicted}'." >&2
    echo "  No side was chosen (merge aborted). Halting; start no next-wave slice." >&2
    exit 1
  fi
done

if [ -n "$TESTCMD" ]; then
  if ! eval "$TESTCMD" >/dev/null 2>&1; then
    echo "build-wave-reconcile: full-suite gate FAILED ('$TESTCMD'). Halting before the next wave." >&2
    exit 1
  fi
fi

echo "build-wave-reconcile: merged ${#sorted[@]} slice branch(es) into '$INTO'; suite gate ${TESTCMD:+passed}${TESTCMD:-skipped}."
