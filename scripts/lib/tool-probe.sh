#!/usr/bin/env bash
# tool-probe.sh — verify a tool by RUNNING it, never by resolving it on PATH.
# SOURCED, not executed.
#
# `command -v foo` answers "is there an executable named foo", which is a
# strictly weaker question than "does foo work" — and the gap is not
# theoretical. dev-setup.sh reported `✓ semgrep` for an install whose native
# `_cffi_backend` extension was missing: the binary resolved fine, and every
# actual invocation died with a ModuleNotFoundError and a Rust panic. The
# suites that depend on it then failed against a toolchain the script had just
# declared ready. "A gate that cannot fail is worse than no gate" (CLAUDE.md),
# and this one could not fail for any tool whose file merely existed.
#
# Living here rather than inline in dev-setup.sh is what makes the fix
# checkable: tests/scripts/test_tool_probe.py sources this file and exercises
# all three outcomes against real working, missing, and crashing commands —
# verifying the runtime property AT RUNTIME, per the same CLAUDE.md rule that
# motivated the change.
#
# The caller is expected to define ok/warn/err/note_failure; plain-text
# fallbacks are installed below when it has not, so this file is sourceable on
# its own.

# Initialized only when the caller has not already done so (dev-setup.sh sets
# it before sourcing), so a standalone source still counts failures.
: "${FAILURES:=0}"

command -v ok           >/dev/null 2>&1 || ok()           { printf '  OK %s\n' "$1"; }
command -v warn         >/dev/null 2>&1 || warn()         { printf '  ~ %s\n' "$1"; }
command -v err          >/dev/null 2>&1 || err()          { printf '  X %s\n' "$1" >&2; }
command -v note_failure >/dev/null 2>&1 || note_failure()  { FAILURES=$((${FAILURES:-0} + 1)); }

# _probe <absent-severity> <label> <absent-note> <command...>
#
# Classifies three outcomes from the probe command's exit status:
#   0    — works. Report ok.
#   127  — the shell could not find the command at all: not installed. Severity
#          is the caller's call (required vs optional).
#   else — installed but FAILED TO RUN. Always a failure, even for an
#          otherwise-optional tool: choosing not to install something is a
#          decision, but a tool that is present and crashes is a broken
#          environment that will fail the gates later, far from its cause.
#          This is the exact case that used to report a green check.
#
# Returns 0 when the tool works, 1 otherwise.
_probe() {
  _probe_absent_severity=$1
  _probe_label=$2
  _probe_absent_note=$3
  shift 3

  _probe_out=$("$@" 2>&1)
  _probe_status=$?

  if [ "$_probe_status" -eq 0 ]; then
    ok "$_probe_label"
    return 0
  fi

  if [ "$_probe_status" -eq 127 ]; then
    if [ "$_probe_absent_severity" = "required" ]; then
      err "$_probe_label not found${_probe_absent_note:+ — $_probe_absent_note}"
      note_failure
    else
      warn "$_probe_label not found${_probe_absent_note:+ — $_probe_absent_note}"
    fi
    return 1
  fi

  err "$_probe_label is installed but failed to run (exit $_probe_status): $(printf '%s' "$_probe_out" | tr '\n' ' ' | cut -c1-140)"
  note_failure
  return 1
}

# Both wrappers take the same shape — <label> <absent-note> <command...> —
# so the note explaining where a missing tool comes from survives either
# severity. Pass "" for no note.

# Absent => error, fails the run. Broken => error, fails the run.
require_tool() {
  _rt_label=$1
  _rt_note=$2
  shift 2
  _probe required "$_rt_label" "$_rt_note" "$@"
}

# Absent => warning only. Broken => error, fails the run (see _probe).
optional_tool() {
  _ot_label=$1
  _ot_note=$2
  shift 2
  _probe optional "$_ot_label" "$_ot_note" "$@"
}
