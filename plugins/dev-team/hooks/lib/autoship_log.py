#!/usr/bin/env python3
"""Autoship round bookkeeping log.

Appends one JSON line per autoship round to a caller-specified JSONL file,
mirroring the metrics/config-changelog.jsonl convention.

CLI usage:
    python autoship_log.py --log-path <path> --json <json-string>
    python autoship_log.py --log-path <path> --json-file <path-to-json-file>
"""

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

_LIB_DIR = pathlib.Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from atomic_state import append_line_locked

_DELAY_ENV_VAR = "DEV_TEAM_AUTOSHIP_LOG_TEST_DELAY_MS"


def append_round(log_path: str, record: dict) -> None:
    """Append a JSON line to log_path, adding a logged_at ISO timestamp.

    Creates the file and any parent directories if they do not exist.
    Serializes concurrent appends via `atomic_state.append_line_locked`
    (#1889) so two overlapping `/autoship` rounds writing to the same log
    are protected from interleaving their bytes into one corrupted line
    while the lock is held (see `locked_state`'s own fail-open fallback for
    when it might not be). Unlike the fail-open telemetry streams sharing
    this pattern (`boundary_events.py`, `workflow_state.py`,
    `iteration_journal_gate.py`), a write failure here is not swallowed —
    `append_line_locked(fail_open=False)` re-raises it after the lock
    releases, so the CLI still surfaces it as a real error.

    Args:
        log_path: Path to the JSONL file.
        record: Mapping of fields to include in the log entry.
    """
    entry = dict(record)
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()

    path = pathlib.Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(entry) + "\n"
    append_line_locked(path, line, delay_env_var=_DELAY_ENV_VAR, fail_open=False)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append one JSON line to an autoship round log."
    )
    parser.add_argument("--log-path", required=True, help="Path to the JSONL log file.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", dest="json_str", help="JSON object string to append.")
    source.add_argument(
        "--json-file",
        help=(
            "Path to a file containing a JSON object to append — the "
            "--body-file convention applied to this log write, so "
            "agent-derived text (e.g. a synthesized blocked_reason) never "
            "needs to be interpolated into an inline --json shell string."
        ),
    )
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.json_file is not None:
        try:
            with open(args.json_file, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print(
                f"error: could not read --json-file {args.json_file!r}: {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        raw = args.json_str

    try:
        record = json.loads(raw)
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
