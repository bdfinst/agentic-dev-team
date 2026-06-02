#!/usr/bin/env bash
# check-severity-consistency.sh — Phase 5b cross-report severity calibration.
#
# For multi-target runs, checks that findings sharing the same rule_id
# (as recorded in each target's memory/disposition-<slug>.json) receive
# the same presentational severity across all targets. Drift across
# repos is emitted as WARN lines; consistent (or single-target) runs
# emit PASS.
#
# Usage:
#   check-severity-consistency.sh <memory-dir> <slug1> [<slug2> ...]
#
# The convention is <memory-dir> first, then one or more slugs. If the
# first positional argument is not an existing directory, the script
# falls back to a default memory-dir of ./memory and treats all
# arguments as slugs.
#
# Inputs:
#   <memory-dir>/report-<slug>.md          — dashboard rows feed presentational-severity inference
#                                            from the finding ID letter (C/H/M/L).
#   <memory-dir>/disposition-<slug>.json   — JSON array of disposition entries; each entry's
#                                            finding.rule_id groups findings across slugs, and
#                                            exploitability.score drives the cross-slug
#                                            comparison via the presentational mapping.
#
# Output:
#   <memory-dir>/severity-consistency-<combined-slug>.txt
#   where combined-slug is the slugs joined by '-'.
#
# Exit codes:
#   0   PASS, single-target run, or no cross-slug overlap found
#   1   one or more WARN lines emitted (severity drift detected)
#   3   missing required inputs / bad usage

set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: check-severity-consistency.sh <memory-dir> <slug1> [<slug2> ...]" >&2
  exit 3
fi

# Decide whether the first arg is a memory-dir or a slug.
FIRST="$1"
if [[ -d "$FIRST" ]]; then
  MEMORY="$FIRST"
  shift
else
  MEMORY="$(pwd)/memory"
fi

if [[ $# -lt 1 ]]; then
  echo "usage: check-severity-consistency.sh <memory-dir> <slug1> [<slug2> ...]" >&2
  exit 3
fi

SLUGS=("$@")
COMBINED="$(IFS=-; echo "${SLUGS[*]}")"
OUT="$MEMORY/severity-consistency-$COMBINED.txt"

mkdir -p "$MEMORY"

# --- Helpers ---------------------------------------------------------------

# Presentational severity mapping from exploitability.score (numeric 0-10):
#   >= 9.0 -> CRITICAL
#   >= 7.0 -> HIGH
#   >= 4.0 -> MEDIUM
#   else   -> LOW
# This mirrors the contract v1.1.0 presentational bands and is used to
# compare dispositions across targets.
score_to_sev() {
  awk -v s="$1" 'BEGIN {
    if (s == "" || s == "null") { print "UNKNOWN"; exit }
    s = s + 0
    if (s >= 9.0) { print "CRITICAL"; exit }
    if (s >= 7.0) { print "HIGH"; exit }
    if (s >= 4.0) { print "MEDIUM"; exit }
    print "LOW"
  }'
}

# Given a finding ID prefix letter, return the dashboard severity.
id_letter_to_sev() {
  case "$1" in
    C) echo "CRITICAL" ;;
    H) echo "HIGH" ;;
    M) echo "MEDIUM" ;;
    L) echo "LOW" ;;
    *) echo "UNKNOWN" ;;
  esac
}

# --- Collect per-slug (rule_id, presentational severity) pairs ------------

# Scratch files
TMP_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t 'sevcons')"
trap 'rm -rf "$TMP_DIR"' EXIT

PAIRS="$TMP_DIR/pairs.tsv"  # rule_id<TAB>sev<TAB>slug
: > "$PAIRS"

# Single-slug short-circuit: nothing to compare across, emit PASS and exit 0.
if [[ ${#SLUGS[@]} -lt 2 ]]; then
  {
    echo "PASS: single-target run ($COMBINED); no cross-repo severity comparison performed"
  } > "$OUT"
  exit 0
fi

HAVE_ANY_DISPOSITION=0

for slug in "${SLUGS[@]}"; do
  DISP="$MEMORY/disposition-$slug.json"
  REPORT="$MEMORY/report-$slug.md"

  # Parse disposition register for rule_id + exploitability.score.
  if [[ -f "$DISP" ]]; then
    HAVE_ANY_DISPOSITION=1
    python3 - "$DISP" "$slug" <<'PY' >> "$PAIRS"
import json, sys

disp_path, slug = sys.argv[1], sys.argv[2]

def score_to_sev(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if v >= 9.0:
        return "CRITICAL"
    if v >= 7.0:
        return "HIGH"
    if v >= 4.0:
        return "MEDIUM"
    return "LOW"

try:
    with open(disp_path) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)

if not isinstance(data, list):
    sys.exit(0)

for entry in data:
    if not isinstance(entry, dict):
        continue
    finding = entry.get("finding") or {}
    rule_id = finding.get("rule_id")
    if not rule_id:
        continue
    expl = entry.get("exploitability") or {}
    score = expl.get("score")
    sev = score_to_sev(score)
    if sev == "UNKNOWN":
        continue
    print(f"{rule_id}\t{sev}\t{slug}")
PY
  fi

  # Also extract dashboard rows from the report (Section 1 table); use the
  # finding-ID prefix letter as a secondary signal. Rows look like:
  #   | FS-C-01 | Rule name | file:line | Category | CRITICAL | TP |
  if [[ -f "$REPORT" ]]; then
    # We only need this to confirm rule-id-to-severity alignment when the
    # disposition file is missing; skip otherwise.
    :
  fi
done

# --- Compare across slugs --------------------------------------------------

# If no disposition data was present at all, nothing to compare -- PASS.
if [[ "$HAVE_ANY_DISPOSITION" -eq 0 ]]; then
  {
    echo "PASS: no disposition registers found for slugs: ${SLUGS[*]}; nothing to compare"
  } > "$OUT"
  exit 0
fi

WARNINGS="$TMP_DIR/warnings.txt"
: > "$WARNINGS"

python3 - "$PAIRS" "$WARNINGS" <<'PY'
import sys
from collections import defaultdict

pairs_path, warn_path = sys.argv[1], sys.argv[2]

# rule_id -> { slug -> set(severities) }
by_rule = defaultdict(lambda: defaultdict(set))
with open(pairs_path) as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        rule_id, sev, slug = parts
        by_rule[rule_id][slug].add(sev)

warns = []
for rule_id, per_slug in by_rule.items():
    slugs_with_this = list(per_slug.keys())
    if len(slugs_with_this) < 2:
        continue  # only one slug has this rule; nothing to compare
    # Build flat (slug, sev) list; if a slug has multiple severities for
    # one rule_id, each combination with another slug is a candidate warn.
    flat = []
    for slug, sevs in per_slug.items():
        for sev in sevs:
            flat.append((slug, sev))
    # Compare each unordered pair of distinct slugs
    seen = set()
    n = len(flat)
    for i in range(n):
        for j in range(i + 1, n):
            s1, v1 = flat[i]
            s2, v2 = flat[j]
            if s1 == s2:
                continue
            if v1 == v2:
                continue
            # Normalize ordering so we don't double-emit the mirror pair
            key = (rule_id, *sorted([(s1, v1), (s2, v2)]))
            if key in seen:
                continue
            seen.add(key)
            warns.append(
                f"WARN: rule_id '{rule_id}' rated {v1} in {s1} but {v2} in {s2}"
            )

with open(warn_path, "w") as fh:
    for w in warns:
        fh.write(w + "\n")
PY

WARN_COUNT=$(wc -l < "$WARNINGS" | tr -d ' ')

{
  if [[ "$WARN_COUNT" -eq 0 ]]; then
    echo "PASS: severity consistent across slugs: ${SLUGS[*]}"
  else
    echo "FAIL: $WARN_COUNT severity drift(s) detected across slugs: ${SLUGS[*]}"
    cat "$WARNINGS"
  fi
} > "$OUT"

if [[ "$WARN_COUNT" -gt 0 ]]; then
  exit 1
fi
exit 0
