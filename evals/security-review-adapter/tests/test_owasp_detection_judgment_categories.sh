#!/usr/bin/env bash
# Every judgment-only pattern row in owasp-detection.md declares a Category cell.
# Judgment-only set is derived from the mapping YAML's security-review.* entries.
# AC-12 (judgment-only subset).
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DOC="$REPO_ROOT/plugins/agentic-dev-team/knowledge/owasp-detection.md"
MAP="$REPO_ROOT/plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml"

python3 - "$DOC" "$MAP" <<'PY'
import re, sys, pathlib, yaml
doc = pathlib.Path(sys.argv[1]).read_text()
mapping = yaml.safe_load(pathlib.Path(sys.argv[2]).read_text())["mappings"]

# Derive judgment-only category set (values starting with security-review.)
judgment_categories = sorted(
    k for k, v in mapping.items() if str(v).startswith("security-review.")
)
if not judgment_categories:
    print("FAIL: no judgment categories in mapping", file=sys.stderr); sys.exit(1)

# For each judgment category, assert its ID appears somewhere in owasp-detection.md.
# The Step 4 convention: annotate each judgment-only row with its Category ID cell.
missing = [c for c in judgment_categories if c not in doc]
if missing:
    print(f"FAIL: judgment categories missing annotation in {sys.argv[1]}:", file=sys.stderr)
    for c in missing:
        print(f"  - {c}", file=sys.stderr)
    sys.exit(1)

# Pattern-visible set must NOT have been annotated yet (that is Item 3b).
# We don't hard-assert their absence here (pattern-visible rows MAY mention
# the string without being annotated), but we do assert the header comment
# about Item 3b is present so reviewers know the scope.
if "Item 3b" not in doc and "item 3b" not in doc.lower():
    print("FAIL: owasp-detection.md missing the 'Item 3b' scope comment "
          "for pattern-visible rows", file=sys.stderr)
    sys.exit(1)

print(f"OK owasp-detection judgment-only annotations ({len(judgment_categories)} categories)")
PY
