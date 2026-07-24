"""Raw-log tier — worst-session flagging + privacy guard (#180, Delta A/B).

The metrics digest is cheap but blind to *semantic* frictions (a hallucinated
citation, an operator habit). The raw-log tier reads the few WORST sessions in
full to surface those — but only the worst (cost is bounded), and its output must
stay metrics-only (no quoted prompt/code/paths).

This module is the deterministic half:
  * `worst_sessions` ranks sessions by a friction score and returns the top-N —
    the GATE that keeps the expensive raw pass off everything else.
  * `validate_finding` enforces the privacy boundary on a tier finding: only
    metrics/ids/enums, never a quote, snippet, path, or free-text payload.

The live per-log agent pass and the methodology lens are run-rawlog-tier.sh's job;
every finding it produces must pass `validate_finding` before it is kept.

Inputs (CLI)
------------
--flag DIR [--top N]   rank sessions in DIR's digests, print the worst N.
--validate FILE        check a JSON findings list against the privacy boundary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_extract import _REWORK_KEYS, _iter_records

# A tier finding may carry ONLY these keys — all metrics/ids/enums.
_ALLOWED_FINDING_KEYS = {
    "session_id", "project", "host", "friction_type", "lens",
    "target_artifact", "confidence", "count",
}
_ALLOWED_LENSES = {"methodology", "harness", "devex", "accuracy"}
# A value that looks like a path or code payload leaks raw content.
_LEAKY_VALUE_RE = re.compile(r"[/\\]|```|def |class |function |SELECT |<script")


def _friction_score(rec: dict) -> float:
    rw = rec.get("rework", {}) if isinstance(rec.get("rework"), dict) else {}
    acc = rec.get("accuracy", {}) if isinstance(rec.get("accuracy"), dict) else {}
    gate = rec.get("gate", {}) if isinstance(rec.get("gate"), dict) else {}
    score = sum(float(rw.get(k, 0) or 0) for k in _REWORK_KEYS)
    score += float(acc.get("user_correction_turns", 0) or 0)
    score += float(acc.get("tool_error_rate", 0.0) or 0.0) * float(acc.get("tool_calls", 0) or 0)
    score += 2.0 * float(gate.get("commit_bypasses", 0) or 0)   # bypass weighted
    return round(score, 4)


def worst_sessions(digests_root: Path, top: int = 5) -> list[dict]:
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if rec.get("schema") == "session-sync/v1" and rec.get("session_id"):
                by_id[str(rec["session_id"])] = rec
    ranked = sorted(
        ({"session_id": sid, "project": r.get("project", "?"),
          "host": r.get("host", "?"), "friction_score": _friction_score(r)}
         for sid, r in by_id.items()),
        key=lambda d: (-d["friction_score"], d["session_id"]),
    )
    return ranked[:max(top, 0)]


def validate_finding(finding: dict) -> list[str]:
    """Return privacy violations for one tier finding; empty == clean."""
    violations = []
    if not isinstance(finding, dict):
        return ["finding is not an object"]
    extra = set(finding) - _ALLOWED_FINDING_KEYS
    if extra:
        violations.append(f"disallowed keys (possible payload leak): {sorted(extra)}")
    lens = finding.get("lens")
    if lens is not None and lens not in _ALLOWED_LENSES:
        violations.append(f"unknown lens {lens!r}")
    for k, v in finding.items():
        if isinstance(v, str) and _LEAKY_VALUE_RE.search(v):
            violations.append(f"field {k!r} looks like a path/code payload")
    return violations


def validate_findings(findings: list) -> dict:
    rows = [{"index": i, "violations": validate_finding(f)} for i, f in enumerate(findings)]
    bad = [r for r in rows if r["violations"]]
    return {"schema": "rawlog-validation/v1", "findings": len(findings),
            "clean": len(findings) - len(bad), "violations": bad,
            "ok": not bad}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flag", metavar="DIR", help="rank sessions, print worst N")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--validate", metavar="FILE", help="check a findings JSON list")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)

    if args.flag:
        result = {"schema": "rawlog-flagged/v1", "top": args.top,
                  "worst_sessions": worst_sessions(Path(args.flag), args.top)}
    elif args.validate:
        findings = json.loads(Path(args.validate).read_text())
        result = validate_findings(findings if isinstance(findings, list) else [])
    else:
        ap.error("one of --flag or --validate is required")
        return 2
    out = json.dumps(result, indent=2, sort_keys=True)
    Path(args.out).write_text(out + "\n") if args.out else print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
