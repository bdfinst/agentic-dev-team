#!/usr/bin/env python3
"""make_lesson_fixtures.py — scaffold metrics/config-changelog.jsonl +
metrics/session-digest.jsonl fixtures for /harness-e2e-check's Step 5
(exercising the real, non-mocked `skills/harness-audit/scripts/lesson_validate.py`
against `--mode validated|harmful|insufficient`).

The schema here is load-bearing and easy to get wrong by guessing: digest
records key their timestamp as `recorded_at` (not `timestamp`), and `rework`
is a dict of sub-metrics summed by `resolve_metric()` (e.g.
`{"failed_edits": 4}`), not a bare number. Issue #907's first live run of
this exact validation used a hand-rolled fixture with both of those wrong —
`timestamp` instead of `recorded_at`, and a bare int for `rework` — and
silently got "insufficient data" back for the wrong reason (no records
matched at all, not "too few"). This script is the corrected, reusable
fixture so that mistake isn't repeated by hand every time.

Usage:
    python3 make_lesson_fixtures.py --target /path/to/scratch --mode validated
    python3 make_lesson_fixtures.py --target /path/to/scratch --mode harmful
    python3 make_lesson_fixtures.py --target /path/to/scratch --mode insufficient
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CHANGELOG_ENTRY = {
    "timestamp": "2026-05-01T00:00:00Z",
    "type": "learn",
    "trigger": "user",
    "description": "Tighten security-review's SSRF detection regex to catch relative-URL bypass",
    "component": "agents/security-review.md",
    "failure_mode_targeted": "SSRF findings missed on relative-URL redirects",
    "predicted_improvement": "security-review eval fixtures for SSRF relative-URL bypass pass",
    "eval_pre": {"passed": 8, "total": 10, "source": "baseline"},
    "eval_post": {"passed": 10, "total": 10, "transcript": ".claude/evals/transcripts/2026-05-01-security-review.json"},
    "eval_verdict": "improved",
    "adoption_status": "adopted",
    "rollback_pointer": "config-changelog:2026-05-01T00:00:00Z",
    "proposed": "Adopt tightened SSRF regex for security-review",
    "evidence_shown": ["commit:abc1234", ".claude/evals/transcripts/2026-05-01-security-review.json"],
    "risks_surfaced": [],
    "approved_by": "user",
    "file_modified": "plugins/dev-team/agents/security-review.md",
    "section_modified": "SSRF detection regex",
    "previous_value": "old regex",
    "new_value": "new regex",
    "evidence": {"metrics": ["rework"], "direction": "decrease", "window_sessions": 10},
}

# (day-range, rework value) pairs. "before" always precedes the adoption
# timestamp (2026-05-01); "after" always follows it.
MODE_WINDOWS = {
    # 12/12, clear improvement -> verdict "validated"
    "validated": {"before": (list(range(19, 31)), 4), "after": (list(range(2, 14)), 1)},
    # 12/12, clear regression (rework went UP against the declared "decrease") -> verdict "harmful"
    "harmful": {"before": (list(range(19, 31)), 1), "after": (list(range(2, 14)), 4)},
    # Only 5/7 records on each side against a window_sessions:10 requirement -> "insufficient data"
    "insufficient": {"before": (list(range(25, 30)), 4), "after": (list(range(2, 9)), 1)},
}


def build_digest(mode: str) -> list[dict]:
    window = MODE_WINDOWS[mode]
    records = []
    before_days, before_rework = window["before"]
    for d in before_days:
        records.append({
            "recorded_at": f"2026-04-{d:02d}T00:00:00Z",
            "rework": {"failed_edits": before_rework},
            "accuracy": {"tool_error_rate": 0.2},
        })
    after_days, after_rework = window["after"]
    for d in after_days:
        records.append({
            "recorded_at": f"2026-05-{d:02d}T00:00:00Z",
            "rework": {"failed_edits": after_rework},
            "accuracy": {"tool_error_rate": 0.1},
        })
    return records


def scaffold(target: Path, mode: str) -> None:
    if mode not in MODE_WINDOWS:
        raise SystemExit(f"--mode must be one of {sorted(MODE_WINDOWS)}, got {mode!r}")

    metrics_dir = target / "metrics"
    memory_dir = target / "memory"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    changelog_path = metrics_dir / "config-changelog.jsonl"
    changelog_path.write_text(json.dumps(CHANGELOG_ENTRY) + "\n", encoding="utf-8")

    digest_path = metrics_dir / "session-digest.jsonl"
    with digest_path.open("w", encoding="utf-8") as f:
        for record in build_digest(mode):
            f.write(json.dumps(record) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path, help="Scratch directory to scaffold into")
    parser.add_argument("--mode", required=True, choices=sorted(MODE_WINDOWS), help="Which verdict this fixture should produce")
    args = parser.parse_args()

    scaffold(args.target, args.mode)
    print(f"Scaffolded {args.mode!r} lesson_validate.py fixture at {args.target}/metrics/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
