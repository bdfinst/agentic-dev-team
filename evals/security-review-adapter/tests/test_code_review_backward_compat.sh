#!/usr/bin/env bash
# /code-review backward compat: the agent's raw JSON (with the new 'category')
# still preserves every field /code-review's renderer consumes, and 'category'
# is the only additive field at issues[]. AC-11.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
FXT="$REPO_ROOT/evals/security-review-adapter/fixtures/agent-output-backward-compat.json"

python3 - "$FXT" <<'PY'
import json, sys, pathlib
obj = json.loads(pathlib.Path(sys.argv[1]).read_text())
# Top-level fields /code-review consumes.
for f in ("status", "issues", "summary"):
    assert f in obj, f"FAIL: missing top-level field {f}"
# Per-issue fields /code-review renderer consumes.
consumed = {"severity", "file", "line", "message", "suggestedFix"}
legacy = consumed | {"confidence"}
additive = {"category"}
for i, issue in enumerate(obj["issues"]):
    present = set(issue.keys())
    missing = consumed - present
    if missing:
        print(f"FAIL: issue[{i}] missing consumed fields {missing}", file=sys.stderr); sys.exit(1)
    extras = present - (legacy | additive)
    if extras:
        print(f"FAIL: issue[{i}] has unexpected additive fields {extras}", file=sys.stderr); sys.exit(1)
    if "category" not in present:
        print(f"FAIL: issue[{i}] missing 'category'", file=sys.stderr); sys.exit(1)
    # Shape checks:
    if not isinstance(issue["severity"], str): sys.exit("FAIL: severity not str")
    if not isinstance(issue["file"], str): sys.exit("FAIL: file not str")
    if not isinstance(issue["line"], int): sys.exit("FAIL: line not int")
    if not isinstance(issue["message"], str): sys.exit("FAIL: message not str")
    if not isinstance(issue["suggestedFix"], str): sys.exit("FAIL: suggestedFix not str")
print("OK /code-review backward compat (category is additive only)")
PY
