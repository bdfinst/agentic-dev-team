#!/usr/bin/env bash
# verify-report.sh — Phase 5c post-generation verification for the exec report.
#
# Runs three automated checks on the generated markdown report:
#
#   1. File:line check (FAIL)
#      Every CRITICAL / HIGH row in the Section 1 dashboard table must have a
#      corresponding Section 2 block containing a `**File:**` or `| File |`
#      line with a path.
#
#   2. Remediation example check (WARN)
#      Every Section 2 block must contain either a fenced code block
#      or a specific command line (starting with RUN, npm, pip, go, kubectl,
#      docker).
#
#   3. Executive-language gate (WARN)
#      Section 0 (Executive Summary) must not contain raw file paths
#      (src/, lib/, *.py, *.ts, *.java outside backtick spans) or CWE-NNN
#      references.
#
# Usage:
#   verify-report.sh <report-file> [<slug>]
#
# If <slug> is supplied, results are written to
# <memory-dir>/verify-report-<slug>.txt where <memory-dir> is the directory
# containing <report-file>; otherwise results are written to stdout.
#
# Exit codes:
#   0   all FAIL checks pass (WARNs OK)
#   1   one or more FAIL checks failed
#   3   missing required inputs / bad usage

set -uo pipefail

REPORT="${1:-}"
SLUG="${2:-}"

if [[ -z "$REPORT" ]]; then
  echo "usage: verify-report.sh <report-file> [<slug>]" >&2
  exit 3
fi

if [[ ! -f "$REPORT" ]]; then
  echo "error: report file not found: $REPORT" >&2
  exit 3
fi

MEMORY_DIR="$(cd "$(dirname "$REPORT")" && pwd)"
if [[ -n "$SLUG" ]]; then
  OUT="$MEMORY_DIR/verify-report-$SLUG.txt"
else
  OUT=""
fi

python3 - "$REPORT" "${OUT:-/dev/stdout}" "$SLUG" <<'PY'
import re
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
out_path = sys.argv[2]
slug = sys.argv[3] if len(sys.argv) > 3 else ""

text = report_path.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines()

# --- Partition into sections by "### Section N" headings -------------------
# We treat everything between "### Section N" markers as that section's body.
section_bounds = []  # list of (name, start_line_idx, end_line_idx_exclusive)
section_re = re.compile(r"^###\s+Section\s+([0-9]+[a-z]?)\b")
current = None
for i, line in enumerate(lines):
    m = section_re.match(line)
    if m:
        if current is not None:
            name, start = current
            section_bounds.append((name, start, i))
        current = (m.group(1), i)
if current is not None:
    name, start = current
    section_bounds.append((name, start, len(lines)))


def section_body(name_prefix):
    """Return the text of the first section whose name starts with name_prefix."""
    for name, s, e in section_bounds:
        if name == name_prefix or name.startswith(name_prefix):
            return "\n".join(lines[s:e])
    return ""


def section_body_exact(name):
    for n, s, e in section_bounds:
        if n == name:
            return "\n".join(lines[s:e])
    return ""


sec0 = section_body_exact("0")
sec1 = section_body_exact("1")
sec2 = section_body_exact("2")

failures = []
warnings = []

# --- Check 1: File:line check ---------------------------------------------
# Dashboard rows look like:
#   | FS-C-01 | Rule name | src/app.py:42 | Category | CRITICAL | TP |
# We extract every row whose ID cell matches a plausible finding ID
# pattern, then filter to CRITICAL / HIGH rows.
crit_high_ids = []
row_re = re.compile(r"^\|\s*([A-Z]{1,4}-[CHML]-\d+)\s*\|")
for line in sec1.splitlines():
    m = row_re.match(line)
    if not m:
        continue
    fid = m.group(1)
    upper = line.upper()
    if "CRITICAL" in upper or "| HIGH " in upper or "|HIGH|" in upper or " HIGH " in upper:
        crit_high_ids.append(fid)

# For each CRITICAL/HIGH ID, find its Section 2 block and verify it contains
# a `**File:**` or `| File |` line with a path.
# A "block" per the agent spec is delimited by an ID heading / mention; we
# search for the ID within Section 2 and scan ~40 lines of context.
sec2_lines = sec2.splitlines()
for fid in crit_high_ids:
    # Locate the ID anywhere in Section 2
    idx = None
    for i, line in enumerate(sec2_lines):
        if fid in line:
            idx = i
            break
    if idx is None:
        failures.append(
            f"FAIL: finding {fid} is CRITICAL/HIGH but has no file:line in Section 2"
        )
        continue
    # Scan a window after the heading for a File indicator.
    window = "\n".join(sec2_lines[idx : idx + 40])
    has_file = (
        re.search(r"\*\*File:\*\*\s*\S", window) is not None
        or re.search(r"\|\s*File\s*\|\s*\S", window) is not None
    )
    if not has_file:
        failures.append(
            f"FAIL: finding {fid} is CRITICAL/HIGH but has no file:line in Section 2"
        )

# --- Check 2: Remediation example check -----------------------------------
# Split Section 2 into per-finding blocks. A block starts at the first line
# that mentions a finding ID and ends at the next such line (or Section end).
block_starts = []
for i, line in enumerate(sec2_lines):
    m = re.search(r"\b([A-Z]{1,4}-[CHML]-\d+)\b", line)
    if m:
        block_starts.append((i, m.group(1)))

blocks = []
for idx, (start, fid) in enumerate(block_starts):
    end = block_starts[idx + 1][0] if idx + 1 < len(block_starts) else len(sec2_lines)
    blocks.append((fid, "\n".join(sec2_lines[start:end])))

cmd_re = re.compile(r"(?m)^\s*(RUN|npm|pip|go|kubectl|docker)\s+\S")
for fid, body in blocks:
    has_fence = "```" in body
    has_cmd = cmd_re.search(body) is not None
    if not (has_fence or has_cmd):
        warnings.append(
            f"WARN: finding {fid} Section 2 block has no code example in remediation"
        )

# --- Check 3: Executive-language gate -------------------------------------
# Strip backtick spans, then search for technical references in Section 0.
def strip_backticks(s):
    # Remove fenced blocks first
    s = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    # Then inline backticks
    s = re.sub(r"`[^`]*`", "", s)
    return s

sec0_clean = strip_backticks(sec0)

tech_patterns = [
    (r"\bsrc/", "src/"),
    (r"\blib/", "lib/"),
    (r"\b\S+\.py\b", ".py"),
    (r"\b\S+\.ts\b", ".ts"),
    (r"\b\S+\.java\b", ".java"),
    (r"\bCWE-\d+\b", "CWE-NNN"),
]

for pat, label in tech_patterns:
    for m in re.finditer(pat, sec0_clean):
        warnings.append(
            f"WARN: Section 0 contains technical reference: {m.group(0)}"
        )

# --- Emit results ---------------------------------------------------------
lines_out = []
if not failures and not warnings:
    lines_out.append(f"PASS: verify-report ({report_path.name}) — all checks clean")
else:
    status = "FAIL" if failures else "PASS"
    lines_out.append(
        f"{status}: verify-report ({report_path.name}) — "
        f"{len(failures)} failure(s), {len(warnings)} warning(s)"
    )
    lines_out.extend(failures)
    lines_out.extend(warnings)

output = "\n".join(lines_out) + "\n"

if out_path == "/dev/stdout":
    sys.stdout.write(output)
else:
    Path(out_path).write_text(output, encoding="utf-8")

sys.exit(1 if failures else 0)
PY
rc=$?
exit "$rc"
