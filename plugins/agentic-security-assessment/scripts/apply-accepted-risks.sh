#!/usr/bin/env bash
# apply-accepted-risks.sh — Phase 1c deterministic accepted-risks suppression.
#
# Parses <target-dir>/ACCEPTED-RISKS.md (a markdown file with a fenced
# ```json block containing an `accepted_risks` array) and suppresses any
# matching finding in <memory-dir>/findings-<slug>.jsonl. One log record
# per suppression is appended to <memory-dir>/accepted-risks-<slug>.jsonl.
#
# Format: the first ```json fenced code block in ACCEPTED-RISKS.md is the
# authoritative suppression list. Free prose outside the block is ignored.
# Using JSON-in-fenced-block avoids a pyyaml dependency (jq parses it).
# Full format reference lives at docs/accepted-risks-format.md.
#
# Matching semantics:
#   - `rule_id`          exact string equality against finding.rule_id
#   - `source_ref_glob`  bash-extglob with globstar against finding.source_ref
#                        (** recurses; * does not cross /).
#   - `expires`          UTC calendar date YYYY-MM-DD; entry active through
#                        that date, expired the day after. Expired entries
#                        are logged with status:expired and do not suppress.
#
# Conventions: matches style of check-severity-consistency.sh + verify-report.sh
# with the same two deliberate deviations documented in phase-timer.sh:
#   1. set -euo pipefail (stricter errexit).
#   2. Four-value exit-code contract (0/1/2/3).
#
# Usage:
#   apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]
#   apply-accepted-risks.sh -h | --help
#
# Exit codes:
#   0  success (zero or more suppressions applied; or no ACCEPTED-RISKS.md)
#   1  runtime error (jq/python3/filesystem)
#   2  (reserved; no missing-input condition is fatal for this script —
#      absent files are treated as "no suppressions declared")
#   3  bad usage OR malformed ACCEPTED-RISKS.md input

set -euo pipefail

usage() {
  cat <<'USAGE'
usage: apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]

If <target-dir>/ACCEPTED-RISKS.md exists with a fenced ```json block,
suppresses any matching entry from <memory-dir>/findings-<slug>.jsonl
and appends one JSONL record per suppression (or one per expired entry)
to <memory-dir>/accepted-risks-<slug>.jsonl.

<memory-dir> defaults to ./memory.

Exit codes:
  0  success
  1  runtime error
  2  (reserved; unused by apply-accepted-risks.sh — absent files are
     treated as a silent no-op with exit 0)
  3  bad usage OR malformed ACCEPTED-RISKS.md (missing required fields /
     invalid JSON in the fenced block)
USAGE
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 3
fi

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 3
fi

TARGET="$1"
SLUG="$2"
MEMORY_DIR="${3:-./memory}"

ARF="$TARGET/ACCEPTED-RISKS.md"
FINDINGS="$MEMORY_DIR/findings-$SLUG.jsonl"
LOG="$MEMORY_DIR/accepted-risks-$SLUG.jsonl"

# Absent ACCEPTED-RISKS.md → silent no-op, exit 0. Caller can wire this
# script unconditionally into Phase 1c.
if [[ ! -f "$ARF" ]]; then
  exit 0
fi

# Extract the first ```json ... ``` block (inclusive of fence markers removed).
JSON_BLOCK="$(awk '
  /^```json[ \t]*$/ { inblock=1; next }
  /^```[ \t]*$/     { if (inblock) { inblock=0; exit } }
  inblock           { print }
' "$ARF")"

if [[ -z "$JSON_BLOCK" ]]; then
  # ACCEPTED-RISKS.md exists but has no ```json block → treat as no-op.
  exit 0
fi

# Validate JSON via jq. On failure, emit parse-error and exit 3.
JQ_ERR=""
if ! JQ_ERR="$(printf '%s' "$JSON_BLOCK" | jq empty 2>&1)"; then
  echo "apply-accepted-risks.sh: ACCEPTED-RISKS.md parse error at $ARF — $JQ_ERR; no risks applied" >&2
  exit 3
fi

# Validate top-level schema: object with `accepted_risks` array of entries,
# each having rule_id + source_ref_glob + reason + expires. Use a heredoc
# with a quoted delimiter so backslashes don't get shell-mangled, and route
# stderr (where the parse-error detail lives) to stdout for capture.
set +e
VALIDATION="$(python3 - "$JSON_BLOCK" <<'PY' 2>&1
import json, sys, re
try:
    data = json.loads(sys.argv[1])
except Exception as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict) or "accepted_risks" not in data:
    print("PARSE_ERROR: top-level object missing accepted_risks array", file=sys.stderr)
    sys.exit(1)
ar = data.get("accepted_risks")
if not isinstance(ar, list):
    print("PARSE_ERROR: accepted_risks is not a list", file=sys.stderr)
    sys.exit(1)
REQUIRED = ("rule_id", "source_ref_glob", "reason", "expires")
DATE_PAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
for i, e in enumerate(ar):
    if not isinstance(e, dict):
        print(f"PARSE_ERROR: entry {i} is not an object", file=sys.stderr)
        sys.exit(1)
    for k in REQUIRED:
        v = e.get(k)
        if not isinstance(v, str) or not v:
            print(f"PARSE_ERROR: entry {i} missing required field {k}", file=sys.stderr)
            sys.exit(1)
    expires_val = e["expires"]
    if not DATE_PAT.match(expires_val):
        print(f"PARSE_ERROR: entry {i} expires not YYYY-MM-DD: {expires_val}", file=sys.stderr)
        sys.exit(1)
print("OK")
PY
)"
VAL_RC=$?
set -e

if [[ $VAL_RC -ne 0 ]]; then
  msg="$(printf '%s' "$VALIDATION" | sed -n 's/^PARSE_ERROR: //p')"
  [[ -n "$msg" ]] || msg="$VALIDATION"
  echo "apply-accepted-risks.sh: ACCEPTED-RISKS.md parse error at $ARF — $msg; no risks applied" >&2
  exit 3
fi

# Findings file is allowed to be absent (no findings = nothing to suppress).
if [[ ! -f "$FINDINGS" ]]; then
  FINDINGS_EXISTS=0
else
  FINDINGS_EXISTS=1
fi

# Ensure memory-dir exists.
mkdir -p "$MEMORY_DIR"

# Today's UTC date for expiry check.
TODAY_UTC="$(python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).date().isoformat())')"
ISO_NOW="$(python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"))')"

FINDINGS_TMP="$FINDINGS.tmp"
LOG_TMP="$LOG.tmp"

# Write the new findings file + log to tmp files, then mv them atomically.
# Globbing uses a hand-rolled glob_to_regex translator (see python block
# below) rather than stdlib fnmatch — the translator is intentional so the
# semantics documented in docs/accepted-risks-format.md ("** recurses, *
# does not cross /") are deterministic across Python versions and match the
# format doc regardless of the host's fnmatch implementation.
set +e
python3 - "$JSON_BLOCK" "$FINDINGS" "$LOG" "$FINDINGS_TMP" "$LOG_TMP" "$TODAY_UTC" "$ISO_NOW" "$FINDINGS_EXISTS" <<'PY'
import json
import re
import sys

(
    json_block,
    findings_path,
    log_path,
    findings_tmp,
    log_tmp,
    today_str,
    iso_now,
    findings_exists_str,
) = sys.argv[1:9]

findings_exists = findings_exists_str == "1"
data = json.loads(json_block)
entries = data["accepted_risks"]

# Translate bash-extglob-style glob to a Python regex so we can apply the
# documented semantics deterministically: `*` matches any chars except `/`;
# `**` matches any chars including `/` (only when it spans a full path
# segment — i.e. "**/..." or ".../**/..." or ".../**"). `?` matches a single
# non-/ char.
def glob_to_regex(glob):
    i = 0
    out = ["^"]
    n = len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            if i + 1 < n and glob[i+1] == "*":
                # consume potential trailing slash for "**/..." form
                if i + 2 < n and glob[i+2] == "/":
                    out.append(r"(?:.*/)?")
                    i += 3
                    continue
                out.append(r".*")
                i += 2
                continue
            out.append(r"[^/]*")
            i += 1
        elif c == "?":
            out.append(r"[^/]")
            i += 1
        elif c in ".+^$(){}|\\":
            out.append("\\" + c)
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return re.compile("".join(out))

# Partition entries into active vs expired.
active = []
expired = []
for e in entries:
    if e["expires"] < today_str:
        expired.append(e)
    else:
        active.append(e)

# Precompile regexes.
for e in active:
    e["_rx"] = glob_to_regex(e["source_ref_glob"])

log_records = []

# First, emit expired-entry log records (stable order: input order).
for e in expired:
    log_records.append({
        "status": "expired",
        "rule_id": e["rule_id"],
        "source_ref_glob": e["source_ref_glob"],
        "reason": e["reason"],
        "expires": e["expires"],
        "iso": iso_now,
    })

surviving = []
if findings_exists:
    with open(findings_path) as f:
        for line in f:
            line_stripped = line.rstrip("\n")
            if not line_stripped:
                continue
            try:
                finding = json.loads(line_stripped)
            except json.JSONDecodeError:
                # Pass malformed lines through unchanged.
                surviving.append(line_stripped)
                continue
            rid = finding.get("rule_id")
            ref = finding.get("source_ref", "")
            matched = None
            for e in active:
                if e["rule_id"] != rid:
                    continue
                if e["_rx"].match(ref):
                    matched = e
                    break
            if matched is not None:
                log_records.append({
                    "status": "suppressed",
                    "rule_id": rid,
                    "source_ref": ref,
                    "source_ref_glob": matched["source_ref_glob"],
                    "reason": matched["reason"],
                    "expires": matched["expires"],
                    "iso": iso_now,
                })
            else:
                surviving.append(line_stripped)

# Write findings_tmp only if findings existed (otherwise nothing to rewrite).
if findings_exists:
    with open(findings_tmp, "w") as f:
        for line in surviving:
            f.write(line + "\n")

# Write log_tmp if we have any records to emit.
if log_records:
    with open(log_tmp, "w") as f:
        for r in log_records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")

PY
PY_RC=$?
set -e

if [[ $PY_RC -ne 0 ]]; then
  rm -f "$FINDINGS_TMP" "$LOG_TMP"
  echo "apply-accepted-risks.sh: python3 stage failed (rc=$PY_RC)" >&2
  exit 1
fi

# Commit atomic rewrites.
if [[ -f "$FINDINGS_TMP" ]]; then
  mv "$FINDINGS_TMP" "$FINDINGS"
fi
if [[ -f "$LOG_TMP" ]]; then
  # Idempotency requires this to be an atomic write (not an append) so
  # re-runs produce byte-identical output.
  mv "$LOG_TMP" "$LOG"
fi
