#!/usr/bin/env bash
# plan-parse.sh — extract per-slice {id, Depends-on, Files} from a plan markdown.
#
# Emits one TSV row per slice:  id<TAB>depends<TAB>files
#   depends: 'none' | a raw list ("1, 2") | '__MISSING__' (no Depends-on line)
#   files:   a raw list ("a, b") | '' (no slice-level Files line)
#
# Only SLICE-LEVEL fields count — the first Depends-on/Files lines under a
# `### Slice <id>:` heading and BEFORE that slice's first `#### Step` heading, so
# per-step `**Files**:` lines are not mistaken for the slice's file surface.
#
# Sourced by plan-waves.sh (provides plan_parse); also runnable standalone.

plan_parse() {
  awk '
  function flush(){ if (id != "") printf "%s\t%s\t%s\n", id, (seen ? deps : "__MISSING__"), files }
  BEGIN { id=""; deps=""; seen=0; files=""; instep=0 }
  /^#+[[:space:]]+[Ss]lice[[:space:]]+/ {
    flush(); line=$0
    sub(/^#+[[:space:]]+[Ss]lice[[:space:]]+/, "", line); sub(/:.*/, "", line)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
    id=line; deps=""; seen=0; files=""; instep=0; next
  }
  /^#{4,}[[:space:]]/ { instep=1 }
  {
    if (id == "" || instep) next
    l = tolower($0)
    if (!seen && l ~ /depends-on[*]*[[:space:]]*:/) {
      v=$0; sub(/.*[Dd]epends-[Oo]n[*]*[[:space:]]*:[[:space:]]*/, "", v)
      gsub(/[*`]/, "", v); gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); deps=v; seen=1
    } else if (files == "" && l ~ /files[*]*[[:space:]]*:/) {
      v=$0; sub(/.*[Ff]iles[*]*[[:space:]]*:[[:space:]]*/, "", v)
      gsub(/[*`]/, "", v); gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); files=v
    }
  }
  END { flush() }
  ' "$1"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  plan_parse "${1:?usage: plan-parse.sh <plan.md>}"
fi
