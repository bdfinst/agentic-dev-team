#!/usr/bin/env bash
# Test: mapping YAML exists, parses, has version + >=21 mappings, every rule_id matches regex.
# Closes AC-2.
set -u
FAIL=0
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MAP="$REPO_ROOT/plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml"

if [[ ! -f "$MAP" ]]; then
  echo "FAIL: mapping file missing at $MAP" >&2
  exit 1
fi

python3 - "$MAP" <<'PY'
import re, sys, yaml
path = sys.argv[1]
with open(path) as fh:
    d = yaml.safe_load(fh)
if not isinstance(d, dict):
    print("FAIL: top-level YAML is not a mapping", file=sys.stderr); sys.exit(1)
if "version" not in d:
    print("FAIL: missing top-level 'version' key", file=sys.stderr); sys.exit(1)
if "mappings" not in d or not isinstance(d["mappings"], dict):
    print("FAIL: missing 'mappings' dict", file=sys.stderr); sys.exit(1)
# version is standalone top-level (not nested inside mappings)
if "version" in d["mappings"]:
    print("FAIL: 'version' nested inside mappings; must be top-level", file=sys.stderr); sys.exit(1)
# version shape: N.N.N
if not isinstance(d["version"], str) or d["version"].count(".") != 2:
    print(f"FAIL: version {d['version']!r} not N.N.N", file=sys.stderr); sys.exit(1)
# >=21 mappings
if len(d["mappings"]) < 21:
    print(f"FAIL: {len(d['mappings'])} mappings, expected >=21", file=sys.stderr); sys.exit(1)
# every rule_id value matches the unified-finding regex
rule_re = re.compile(r"^[a-z0-9_-]+(\.[a-z0-9_-]+)+$")
cat_re = re.compile(r"^A[0-9]{2}\.[a-z0-9-]+$")
bad_rules = [v for v in d["mappings"].values() if not rule_re.fullmatch(str(v))]
bad_cats = [k for k in d["mappings"].keys() if not cat_re.fullmatch(str(k))]
if bad_rules:
    print(f"FAIL: rule_ids not matching regex: {bad_rules}", file=sys.stderr); sys.exit(1)
if bad_cats:
    print(f"FAIL: categories not matching regex: {bad_cats}", file=sys.stderr); sys.exit(1)
print("OK mapping table")
PY
rc=$?
exit $rc
