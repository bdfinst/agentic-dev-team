#!/usr/bin/env bash
# ci-timing.sh — opt-in per-step timing renderer for ci-local.sh. SOURCED, not
# executed.
#
# Pure formatting/aggregation: it reads the per-index timing files ci-local.sh
# writes into $RUNDIR and prints (1) a human-readable timing section and
# (2) an uncolored, machine-parseable block. No git, no side effects beyond
# stdout — so it is unit-testable by seeding a $RUNDIR without running the real
# suite (tests/scripts/test_ci_local_timing.py), mirroring the sourced-pure
# design of scripts/lib/ci-changed-only.sh.
#
# The decision of *whether* to render (the CI_LOCAL_TIMING gate) stays in
# ci-local.sh; this file only knows *how* to format. bash 3.2 safe.

# ci_timing_format_seconds <raw>
# Normalize a raw bash `time`/TIMEFORMAT='%R' value (e.g. "0.007", "1.234") to a
# fixed two-decimal string. Returns non-zero on empty/non-numeric input so the
# caller can substitute a sentinel rather than print a bogus number.
ci_timing_format_seconds() {
  case "$1" in
    '' | *[!0-9.]*) return 1 ;;
  esac
  printf '%.2f' "$1"
}

# ci_timing_seconds_at <time_file>
# Read a per-index (or total) .time file and echo its value formatted to two
# decimals. Echoes '?' when the file is absent or its content is non-numeric.
# Single source of the read-and-format step shared by the human and machine rows.
ci_timing_seconds_at() {
  local raw
  # tail -1: the timed region's stderr may carry stray lines; the %R value is the
  # last line the `time` keyword emits.
  raw="$(tail -n 1 "$1" 2>/dev/null | tr -d '[:space:]')"
  ci_timing_format_seconds "$raw" 2>/dev/null || printf '?'
}

# ci_timing_value_for <rundir> <index>
# The machine value for one check: its formatted seconds when it ran, the literal
# 'skipped' when it was skipped (a --changed-only skip writes <index>.rc but never
# forks a timed subshell, so no <index>.time exists — never report 0.00s, which
# would misread as a real fast pass), or '?' when neither file is present.
ci_timing_value_for() {
  local rundir="$1" i="$2"
  if [ -f "$rundir/$i.time" ]; then
    ci_timing_seconds_at "$rundir/$i.time"
  elif [ -f "$rundir/$i.rc" ]; then
    printf 'skipped'
  else
    printf '?'
  fi
}

# ci_timing_human <value>
# Human rendering of a machine value: numeric -> "<n>s"; any sentinel (skipped,
# ?) is passed through unchanged so it never becomes e.g. "skippeds".
ci_timing_human() {
  case "$1" in
    '' | *[!0-9.]*) printf '%s' "$1" ;;
    *) printf '%ss' "$1" ;;
  esac
}

# ci_render_timing <rundir> [<label0> <label1> ...]
# Print the timing section. <rundir> is ci-local.sh's per-run temp dir: the total
# wall-clock lives at <rundir>/.total.time and each check's own time at
# <rundir>/<i>.time, index-aligned with the declared CHECKS labels passed in
# order. Emits a human-readable section (per-check lines in declared order plus a
# total) and, below it, an uncolored machine-parseable block (label<TAB>seconds)
# so the ranking follow-up need not scrape the human text.
ci_render_timing() {
  local rundir="$1"
  shift
  local labels=("$@")
  local total_val
  total_val="$(ci_timing_seconds_at "$rundir/.total.time")"

  # Read each check's value once, index-aligned with the labels, so the human and
  # machine renderings below share one source of values (a real time, 'skipped',
  # or '?').
  local vals=() i=0
  for _label in ${labels[@]+"${labels[@]}"}; do
    vals+=("$(ci_timing_value_for "$rundir" "$i")")
    i=$((i + 1))
  done

  printf '\n== timing ==\n'
  i=0
  for _label in ${labels[@]+"${labels[@]}"}; do
    printf '  %s  %s\n' "$_label" "$(ci_timing_human "${vals[$i]}")"
    i=$((i + 1))
  done
  printf '  %s  %s\n' "total" "$(ci_timing_human "$total_val")"

  printf '\n-- machine-readable --\n'
  i=0
  for _label in ${labels[@]+"${labels[@]}"}; do
    printf '%s\t%s\n' "$_label" "${vals[$i]}"
    i=$((i + 1))
  done
  printf '%s\t%s\n' "total" "$total_val"
}
