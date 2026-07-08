#!/usr/bin/env python3
"""Autoship round bookkeeping log.

Appends one JSON line per autoship round to a caller-specified JSONL file,
mirroring the metrics/config-changelog.jsonl convention.

CLI usage:
    python autoship_log.py --log-path <path> --json <json-string>
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone


def append_round(log_path: str, record: dict) -> None:
    """Append a JSON line to log_path, adding a logged_at ISO timestamp.

    Creates the file and any parent directories if they do not exist.

    Args:
        log_path: Path to the JSONL file.
        record: Mapping of fields to include in the log entry.
    """
    entry = dict(record)
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()

    path = pathlib.Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append one JSON line to an autoship round log."
    )
    parser.add_argument("--log-path", required=True, help="Path to the JSONL log file.")
    parser.add_argument(
        "--json", required=True, dest="json_str", help="JSON object string to append."
    )
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        record = json.loads(args.json_str)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(record, dict):
        print("error: JSON must be an object (dict)", file=sys.stderr)
        return 1

    append_round(args.log_path, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
