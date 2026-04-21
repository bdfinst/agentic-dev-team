#!/usr/bin/env python3
"""normalize_findings — convert a batch of SARIF documents to unified findings.

Reads every *.sarif file in a directory, runs each through the shared SARIF
parser used by evals/static-analysis-tools/validate.py (same TOOL_TIER_MAP,
same rule-id conventions), deduplicates, and emits findings.jsonl in the
unified finding envelope v1.0 format.

Usage:
    python3 scripts/lib/normalize_findings.py <sarif-dir> <output-jsonl>

If output-jsonl exists, it is overwritten. The shared parser is imported
from evals/static-analysis-tools/validate.py so rule-id conventions stay
in lock-step with that validator.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "evals/static-analysis-tools"))

# Import from the existing validator — keeps rule-id conventions in sync
try:
    from validate import parse_sarif, TOOL_TIER_MAP  # type: ignore[import-not-found]
except ImportError as e:
    print(f"error: cannot import shared parser: {e}", file=sys.stderr)
    print(f"  (expected at {REPO}/evals/static-analysis-tools/validate.py)", file=sys.stderr)
    sys.exit(2)


# Additional driver-name → tier mappings for tools the tier-1 mock tests
# don't exercise but this local script invokes. Extends TOOL_TIER_MAP.
EXTRA_TIER_MAP = {
    "actionlint": "workflows",
    "gitleaks": "secrets",
}
for k, v in EXTRA_TIER_MAP.items():
    TOOL_TIER_MAP.setdefault(k, v)


def dedupe_findings(findings: list[dict]) -> list[dict]:
    """Remove duplicates on (rule_id, file, line). Keep the first occurrence
    but prefer higher-severity duplicates when they clash on location."""
    seen: dict[tuple[str, str, int | None], dict] = {}
    severity_rank = {"error": 4, "warning": 3, "suggestion": 2, "info": 1}
    for f in findings:
        key = (f.get("rule_id", ""), f.get("file", ""), f.get("line"))
        if key not in seen:
            seen[key] = f
        else:
            existing = seen[key]
            if severity_rank.get(f.get("severity", ""), 0) > severity_rank.get(existing.get("severity", ""), 0):
                seen[key] = f
    return list(seen.values())


def process_sarif_file(sarif_path: Path, target_path_prefix: str | None) -> list[dict]:
    try:
        with sarif_path.open() as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [skip] {sarif_path.name}: {e}", file=sys.stderr)
        return []

    if not isinstance(doc, dict) or "runs" not in doc:
        return []

    try:
        findings = parse_sarif(doc)
    except Exception as e:
        print(f"  [skip] {sarif_path.name}: parse error {type(e).__name__}: {e}", file=sys.stderr)
        return []

    # Normalize file paths to target-relative if a target prefix was provided
    if target_path_prefix:
        prefix = target_path_prefix.rstrip("/") + "/"
        for f in findings:
            file = f.get("file", "")
            if file.startswith(prefix):
                f["file"] = file[len(prefix):]

    return findings


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: normalize_findings.py <sarif-dir> <output-jsonl>", file=sys.stderr)
        return 2

    sarif_dir = Path(sys.argv[1])
    output = Path(sys.argv[2])

    if not sarif_dir.is_dir():
        print(f"error: sarif dir not found: {sarif_dir}", file=sys.stderr)
        return 2

    all_findings: list[dict] = []
    for sarif_file in sorted(sarif_dir.glob("*.sarif")):
        findings = process_sarif_file(sarif_file, target_path_prefix=None)
        print(f"  {sarif_file.name}: {len(findings)} finding(s)", file=sys.stderr)
        all_findings.extend(findings)

    # Dedupe
    before = len(all_findings)
    all_findings = dedupe_findings(all_findings)
    print(f"Normalized {before} → {len(all_findings)} findings after dedup", file=sys.stderr)

    # Emit JSONL
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as f:
        for finding in all_findings:
            f.write(json.dumps(finding) + "\n")
    print(f"wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
