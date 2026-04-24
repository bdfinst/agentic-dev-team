#!/usr/bin/env bash
# AST-level single-source-of-truth check. AC-13.
# No string literal in the adapter source equals any mapping rule_id,
# nor matches the '^semgrep\.' pattern, EXCEPT the allowed prefix constant
# 'security-review.' used for the fallback path.
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ADAPTER="$REPO_ROOT/plugins/agentic-dev-team/skills/static-analysis-integration/adapters/security-review-adapter.py"
MAP="$REPO_ROOT/plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml"

python3 - "$ADAPTER" "$MAP" <<'PY'
import ast, re, sys, yaml, pathlib
source = pathlib.Path(sys.argv[1]).read_text()
tree = ast.parse(source)
mapping = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())["mappings"]
rule_ids = set(str(v) for v in mapping.values())

SEMGREP_RE = re.compile(r"^semgrep\.")
# Allowed prefix constant for the fallback path.
ALLOWED = {"security-review."}

violations = []
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
        if s in ALLOWED:
            continue
        if s in rule_ids:
            violations.append((node.lineno, s, "matches a YAML rule_id"))
        elif SEMGREP_RE.match(s):
            violations.append((node.lineno, s, "matches ^semgrep\\."))

if violations:
    print("FAIL: rule_id literal(s) in adapter source:", file=sys.stderr)
    for lineno, s, reason in violations:
        print(f"  line {lineno}: {s!r} ({reason})", file=sys.stderr)
    sys.exit(1)

print("OK single-source-of-truth AST")
PY
