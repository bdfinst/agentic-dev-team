#!/usr/bin/env bash
# audit-rules-vs-prompts.sh — enforcement sensor for the rules-vs-prompts
# boundary (issue #118). Converts the removed rules-vs-prompts-policy.md from
# prose into a mechanical gate over the policy-as-data in
# plugins/dev-team/knowledge/security-review-rule-map.yaml.
#
# FAILS (exit 1) when:
#   1. a class declares an invalid `surface` (not rule|prompt|both);
#   2. surface/rule_id namespace mismatch — a prompt class not in the
#      security-review.* namespace, or a rule/both class not adopting an
#      upstream semgrep.* rule_id (cross-surface duplication the policy forbids);
#   3. a rule/both class lacks fixtures (>=1 positive + >=1 negative) or a
#      measured fp_rate;
#   4. any fp_rate exceeds the policy's <=0.10 threshold (demotion candidate);
#   5. owasp-detection.md lists an agent *detection row* (a `|`-table row) for a
#      class marked rule-surface — those classes must appear only as pointers.
#
# Test seams (env vars): RULE_MAP, OWASP_DOC, PLUGIN_ROOT.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="${PLUGIN_ROOT:-$REPO_ROOT/plugins/dev-team}"
RULE_MAP="${RULE_MAP:-$PLUGIN_ROOT/knowledge/security-review-rule-map.yaml}"
OWASP_DOC="${OWASP_DOC:-$PLUGIN_ROOT/knowledge/owasp-detection.md}"

python3 - "$RULE_MAP" "$OWASP_DOC" "$PLUGIN_ROOT" <<'PY'
import sys, re
from pathlib import Path
try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed (pip install pyyaml / apt install python3-yaml)",
          file=sys.stderr)
    sys.exit(2)

rule_map_path, owasp_path, plugin_root = sys.argv[1], sys.argv[2], Path(sys.argv[3])
data = yaml.safe_load(Path(rule_map_path).read_text())
mappings = data.get("mappings", {}) or {}
classes = data.get("classes", {}) or {}
owasp = Path(owasp_path).read_text() if Path(owasp_path).exists() else ""
THRESHOLD = 0.10

fails = []
if not classes:
    fails.append("manifest has no `classes:` policy section")

for cls, meta in classes.items():
    if not isinstance(meta, dict):
        fails.append(f"{cls}: class entry must be a mapping")
        continue
    surface = meta.get("surface")
    if surface not in ("rule", "prompt", "both"):
        fails.append(f"{cls}: invalid surface {surface!r} (rule|prompt|both)")
        continue

    rule_id = mappings.get(cls)
    if rule_id is None:
        fails.append(f"{cls}: surface={surface} but no rule_id in `mappings`")
    else:
        # Check 2: surface <-> namespace consistency (no cross-surface dup).
        if surface == "prompt" and not rule_id.startswith("security-review."):
            fails.append(f"{cls}: prompt-surface but rule_id {rule_id!r} is not "
                         f"in the security-review.* namespace (looks rule-detectable "
                         f"— a class on two surfaces)")
        if surface in ("rule", "both") and not rule_id.startswith("semgrep."):
            fails.append(f"{cls}: {surface}-surface but rule_id {rule_id!r} does "
                         f"not adopt an upstream semgrep.* id (policy Q4)")

    if surface in ("rule", "both"):
        # Check 3: fp_rate present + numeric.
        fp = meta.get("fp_rate")
        if not isinstance(fp, (int, float)):
            fails.append(f"{cls}: {surface}-surface class lacks a measured fp_rate")
        elif fp > THRESHOLD:  # Check 4: demotion candidate.
            fails.append(f"{cls}: fp_rate {fp} exceeds {THRESHOLD} — DEMOTION "
                         f"CANDIDATE, move to surface: prompt until tightened")
        # Check 3: fixtures dir with >=1 positive + >=1 negative.
        fxrel = meta.get("fixtures")
        if not fxrel:
            fails.append(f"{cls}: {surface}-surface class has no `fixtures` pointer")
        else:
            fxdir = plugin_root / fxrel
            pos = list(fxdir.glob("positive.*")) if fxdir.is_dir() else []
            neg = list(fxdir.glob("negative.*")) if fxdir.is_dir() else []
            if not pos or not neg:
                fails.append(f"{cls}: fixtures {fxrel} need >=1 positive.* and "
                             f">=1 negative.* (found pos={len(pos)} neg={len(neg)})")

    # Check 5: rule-surface class must not be an agent detection ROW in owasp doc.
    if surface == "rule":
        for line in owasp.splitlines():
            s = line.strip()
            if s.startswith("|") and cls in s:
                fails.append(f"{cls}: rule-surface class appears as an agent "
                             f"detection row in owasp-detection.md (must be a "
                             f"pointer, not a detection row): {s[:80]}")
                break

if fails:
    print("rules-vs-prompts audit FAILED:")
    for f in fails:
        print(f"  ✗ {f}")
    sys.exit(1)

rule_n = sum(1 for m in classes.values() if isinstance(m, dict) and m.get("surface") in ("rule", "both"))
print(f"rules-vs-prompts audit OK: {len(classes)} classes "
      f"({rule_n} rule/both with fixtures + fp_rate <= {THRESHOLD}).")
PY
