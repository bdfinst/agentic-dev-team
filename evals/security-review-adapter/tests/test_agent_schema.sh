#!/usr/bin/env bash
# Agent output JSON schema block contains 'category' on issues[], and prose
# documents the regex ^A[0-9]{2}\.[a-z0-9-]+$. AC-1.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
AGENT="$REPO_ROOT/plugins/agentic-dev-team/agents/security-review.md"

if [[ ! -f "$AGENT" ]]; then
  echo "FAIL: agent file missing at $AGENT" >&2
  exit 1
fi

# Locate the Output JSON block and grep inside it for "category"
python3 - "$AGENT" <<'PY'
import re, sys, pathlib
text = pathlib.Path(sys.argv[1]).read_text()
# Match the first fenced json block after "Output JSON:"
m = re.search(r"Output JSON:\s*\n+```json\n(.*?)\n```", text, flags=re.S)
if not m:
    print("FAIL: no 'Output JSON:' fenced ```json block", file=sys.stderr)
    sys.exit(1)
block = m.group(1)
if '"category"' not in block:
    print("FAIL: 'category' not present in Output JSON block", file=sys.stderr)
    print(block, file=sys.stderr)
    sys.exit(1)
# Regex prose: the document must mention the required-format regex somewhere
if r"A[0-9]{2}\.[a-z0-9-]+" not in text:
    print("FAIL: category regex ^A[0-9]{2}\\.[a-z0-9-]+$ not documented in prose", file=sys.stderr)
    sys.exit(1)
print("OK agent schema carries category + regex")
PY
