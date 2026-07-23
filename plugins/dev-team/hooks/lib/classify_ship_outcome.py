"""
classify_ship_outcome.py — deterministic /ship outcome classifier.

Reads metrics/review-value.jsonl and metrics/verify-log.jsonl since a
start timestamp and returns one of three outcome strings:

  "convergence_failure" — any review-value entry since `since_iso` has
                          outcome == "escalated"
  "success"             — at least one verify-log entry since `since_iso`
                          has outcome in {"ran", "failed-then-fixed"}
  "unrecognized"        — neither condition met (or no matching entries)

Files that do not exist are treated as empty (no lines).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional


_VERIFY_SUCCESS_OUTCOMES = {"ran", "failed-then-fixed"}


def _timestamp_field(record: dict) -> Optional[str]:
    """Return the timestamp string from a JSONL record, trying common field names."""
    for key in ("timestamp", "logged_at", "ts"):
        if key in record:
            return str(record[key])
    return None


def _read_since(path: Path, since_iso: str) -> List[dict]:
    """
    Return all JSON records from *path* whose timestamp >= since_iso.

    Lines that are not valid JSON, or that have no recognisable timestamp
    field, are skipped silently.
    """
    if not path.exists():
        return []

    results: List[dict] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = _timestamp_field(record)
            if ts is not None and ts < since_iso:
                continue
            results.append(record)
    return results


def classify(
    review_value_path: Path,
    verify_log_path: Path,
    since_iso: str,
) -> str:
    """
    Classify the /ship outcome from two JSONL metric files.

    Parameters
    ----------
    review_value_path:
        Path to metrics/review-value.jsonl (may not exist).
    verify_log_path:
        Path to metrics/verify-log.jsonl (may not exist).
    since_iso:
        ISO-8601 timestamp string.  Only records at or after this time
        are considered.

    Returns
    -------
    One of "convergence_failure", "success", or "unrecognized".
    """
    review_records = _read_since(Path(review_value_path), since_iso)
    if any(r.get("outcome") == "escalated" for r in review_records):
        return "convergence_failure"

    verify_records = _read_since(Path(verify_log_path), since_iso)
    if any(r.get("outcome") in _VERIFY_SUCCESS_OUTCOMES for r in verify_records):
        return "success"

    return "unrecognized"


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify /ship outcome from JSONL metric files."
    )
    parser.add_argument(
        "--review-value",
        required=True,
        metavar="PATH",
        help="Path to metrics/review-value.jsonl",
    )
    parser.add_argument(
        "--verify-log",
        required=True,
        metavar="PATH",
        help="Path to metrics/verify-log.jsonl",
    )
    parser.add_argument(
        "--since",
        required=True,
        metavar="ISO_TIMESTAMP",
        help="Consider only records at or after this ISO-8601 timestamp",
    )
    args = parser.parse_args()

    result = classify(
        review_value_path=Path(args.review_value),
        verify_log_path=Path(args.verify_log),
        since_iso=args.since,
    )
    print(result)


if __name__ == "__main__":
    _main()
