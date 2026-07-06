#!/usr/bin/env python3
"""Validated-outcome weighting for feedback-learning lessons (#866).

Reads `metrics/config-changelog.jsonl` (written by `/feedback-learning`) and
`metrics/session-digest.jsonl` (written by `/session-review`) and, for every
adopted lesson that carries a structured `evidence` field and whose
observation window has elapsed, compares the watched metric before vs. after
adoption and records a verdict:

  validated         watched metric moved in the expected `direction`
  neutral           window elapsed, adequate data, no meaningful movement
  harmful           watched metric moved against the expected `direction`
  insufficient data fewer than `window_sessions` digest records exist on
                    either side of adoption — never reported as `neutral`

Lessons whose `evidence` is the literal string `"unmeasurable"`, or that
predate the `evidence` field entirely (legacy), are counted but never
assigned a verdict and never proposed for rollback on evidence grounds.

This module is a pure library + a thin CLI. `/harness-audit` is report-only
(it does not modify agents or configuration) — this script mirrors that: it
can *append* new `type: "validation"` entries to the changelog (append-only,
mirroring how rollbacks are already logged as new entries), but it never
rewrites or deletes an existing line, and a `harmful` verdict only ever
produces a rollback *proposal* for a human to action via `/feedback-learning`
— never an automatic rollback.

Usage:
  lesson_validate.py --changelog metrics/config-changelog.jsonl \
                      --digest metrics/session-digest.jsonl \
                      [--apply] [-o report.json]

  --apply   append `type: "validation"` entries for every newly-judged
            lesson to the changelog file (still append-only). Without
            --apply, the report is computed but nothing is written.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LESSON_TYPES = {"amend", "learn", "remember"}
DEFAULT_WINDOW_SESSIONS = 10
DEFAULT_METRIC = "rework"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file, skipping blank/malformed lines. Missing file -> []."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Append records to a JSONL file. Never truncates or rewrites — the file
    is opened in append mode only, so every pre-existing byte is preserved."""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Evidence field validation (Acceptance Criterion: "declare evidence or opt out")
# ---------------------------------------------------------------------------


def has_valid_evidence(entry: dict[str, Any]) -> bool:
    """True if a lesson-type entry's `evidence` field is either the literal
    string "unmeasurable" or a structured object with metrics/direction/
    window_sessions. False if absent or malformed."""
    if "evidence" not in entry:
        return False
    evidence = entry["evidence"]
    if evidence == "unmeasurable":
        return True
    if isinstance(evidence, dict):
        return (
            isinstance(evidence.get("metrics"), list)
            and evidence.get("metrics")
            and evidence.get("direction") in ("increase", "decrease")
            and isinstance(evidence.get("window_sessions"), int)
        )
    return False


def default_evidence(metrics: list[str] | None = None) -> dict[str, Any]:
    """The default structured evidence block when a lesson author names a
    metric but not a window, or names nothing at all (maintainer-resolved
    default: metric=rework, window=10 — see issue #866 Ambiguity Log)."""
    return {
        "metrics": metrics or [DEFAULT_METRIC],
        "direction": "decrease",
        "window_sessions": DEFAULT_WINDOW_SESSIONS,
    }


# ---------------------------------------------------------------------------
# Classification: structured evidence / unmeasurable / legacy
# ---------------------------------------------------------------------------


def classify_changelog_entries(
    entries: list[dict[str, Any]],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split lesson-type changelog entries into (structured, unmeasurable,
    legacy). Only `amend`/`learn`/`remember` entries are lessons; `rollback`
    and `validation` entries are ignored here."""
    structured: list[dict] = []
    unmeasurable: list[dict] = []
    legacy: list[dict] = []
    for entry in entries:
        if entry.get("type") not in LESSON_TYPES:
            continue
        evidence = entry.get("evidence")
        if "evidence" not in entry:
            legacy.append(entry)
        elif evidence == "unmeasurable":
            unmeasurable.append(entry)
        elif isinstance(evidence, dict) and has_valid_evidence(entry):
            structured.append(entry)
        else:
            # Malformed evidence value — treat conservatively as legacy
            # (surfaced, never judged) rather than guessing a verdict.
            legacy.append(entry)
    return structured, unmeasurable, legacy


# ---------------------------------------------------------------------------
# Metric resolution over session-digest.jsonl records
# ---------------------------------------------------------------------------


def resolve_metric(record: dict[str, Any], metric_name: str) -> float | None:
    """Resolve a metric name to a numeric value on a session-digest record.
    Supports the named aggregate aliases plus a dotted-path fallback (e.g.
    "rework.failed_edits")."""
    if metric_name == "rework":
        rework = record.get("rework")
        if not isinstance(rework, dict):
            return None
        values = [v for v in rework.values() if isinstance(v, (int, float))]
        return float(sum(values)) if values else None
    if metric_name == "accuracy":
        accuracy = record.get("accuracy")
        if not isinstance(accuracy, dict):
            return None
        val = accuracy.get("tool_error_rate")
        return float(val) if isinstance(val, (int, float)) else None
    if metric_name == "cost_usd":
        val = record.get("cost_usd")
        return float(val) if isinstance(val, (int, float)) else None

    node: Any = record
    for part in metric_name.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if isinstance(node, (int, float)) else None


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------

INSUFFICIENT_DATA = "insufficient data"


def validate_lesson(
    entry: dict[str, Any], digest_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compute a verdict for one structured-evidence lesson entry against the
    session-digest stream. Direction-only comparison of window means (v1 —
    no significance testing, per the issue's Ambiguity Log)."""
    evidence = entry["evidence"]
    metric_name = evidence["metrics"][0]
    direction = evidence["direction"]
    window = evidence["window_sessions"]
    adoption_ts = _parse_ts(entry["timestamp"])

    dated = []
    for record in digest_records:
        ts = record.get("recorded_at")
        if not ts:
            continue
        try:
            dated.append((_parse_ts(ts), record))
        except ValueError:
            continue
    dated.sort(key=lambda pair: pair[0])

    before = [record for ts, record in dated if ts < adoption_ts]
    after = [record for ts, record in dated if ts >= adoption_ts]

    # Small-N honesty: fewer records than the declared window on either side
    # is a data condition, never a "neutral" judgment.
    if len(before) < window or len(after) < window:
        return {
            "verdict": INSUFFICIENT_DATA,
            "references_timestamp": entry["timestamp"],
            "metric": metric_name,
        }

    before_window = before[-window:]
    after_window = after[:window]

    before_vals = [
        v for v in (resolve_metric(r, metric_name) for r in before_window) if v is not None
    ]
    after_vals = [
        v for v in (resolve_metric(r, metric_name) for r in after_window) if v is not None
    ]

    if len(before_vals) < window or len(after_vals) < window:
        return {
            "verdict": INSUFFICIENT_DATA,
            "references_timestamp": entry["timestamp"],
            "metric": metric_name,
        }

    before_mean = statistics.fmean(before_vals)
    after_mean = statistics.fmean(after_vals)

    if after_mean == before_mean:
        verdict = "neutral"
    elif direction == "decrease":
        verdict = "validated" if after_mean < before_mean else "harmful"
    else:  # direction == "increase"
        verdict = "validated" if after_mean > before_mean else "harmful"

    return {
        "verdict": verdict,
        "references_timestamp": entry["timestamp"],
        "metric": metric_name,
        "direction": direction,
        "before_mean": before_mean,
        "after_mean": after_mean,
        "window_sessions": window,
    }


def build_validation_entry(
    entry: dict[str, Any], result: dict[str, Any], *, now: str | None = None
) -> dict[str, Any]:
    """Build a new `type: "validation"` changelog entry for a verdict. This is
    always a *new* entry — callers must append it, never edit history."""
    return {
        "timestamp": now or _now_iso(),
        "type": "validation",
        "trigger": "system",
        "description": (
            f"Lesson validation for entry {entry['timestamp']}: "
            f"{result['verdict']}"
        ),
        "references_timestamp": entry["timestamp"],
        "verdict": result["verdict"],
        "metric": result.get("metric"),
        "before_mean": result.get("before_mean"),
        "after_mean": result.get("after_mean"),
        "approved_by": "system",
    }


def build_rollback_proposal(entry: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Build a rollback *proposal* for a harmful verdict. Carries everything
    `/feedback-learning`'s existing rollback flow needs, but this is never
    applied automatically — a human must approve it."""
    return {
        "proposal": "rollback",
        "verdict": "harmful",
        "references_timestamp": entry["timestamp"],
        "timestamp": entry.get("timestamp"),
        "file_modified": entry.get("file_modified"),
        "section_modified": entry.get("section_modified"),
        "previous_value": entry.get("previous_value"),
        "requires_human_approval": True,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(
    changelog_entries: list[dict[str, Any]], digest_records: list[dict[str, Any]]
) -> dict[str, Any]:
    structured, unmeasurable, legacy = classify_changelog_entries(changelog_entries)

    verdicts = []
    new_validation_entries = []
    rollback_proposals = []
    for entry in structured:
        result = validate_lesson(entry, digest_records)
        verdicts.append({"entry": entry, "result": result})
        new_validation_entries.append(build_validation_entry(entry, result))
        if result["verdict"] == "harmful":
            rollback_proposals.append(build_rollback_proposal(entry, result))

    return {
        "verdicts": verdicts,
        "new_validation_entries": new_validation_entries,
        "rollback_proposals": rollback_proposals,
        "unmeasurable_count": len(unmeasurable),
        "legacy_count": len(legacy),
        "structured_count": len(structured),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", required=True, type=Path)
    parser.add_argument("--digest", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Append validation entries")
    parser.add_argument("-o", "--output", type=Path, help="Write JSON report here")
    args = parser.parse_args(argv)

    changelog_entries = read_jsonl(args.changelog)
    digest_records = read_jsonl(args.digest)
    report = build_report(changelog_entries, digest_records)

    if args.apply:
        append_jsonl(args.changelog, report["new_validation_entries"])

    output_json = json.dumps(
        {
            "structured_count": report["structured_count"],
            "unmeasurable_count": report["unmeasurable_count"],
            "legacy_count": report["legacy_count"],
            "verdicts": [
                {
                    "references_timestamp": v["result"].get("references_timestamp"),
                    "verdict": v["result"]["verdict"],
                    "metric": v["result"].get("metric"),
                }
                for v in report["verdicts"]
            ],
            "rollback_proposals": report["rollback_proposals"],
        },
        indent=2,
        sort_keys=True,
    )
    if args.output:
        args.output.write_text(output_json + "\n", encoding="utf-8")
    else:
        print(output_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
