#!/usr/bin/env python3
"""metrics_query.py — typed/faceted query helper over metrics event streams (#1169).

`dev-team`'s `metrics/*.jsonl` streams (see `knowledge/telemetry-schema.md`)
are greppable but every consumer hand-rolls `jq`. This is a thin, generic
filter/facet reader over any single stream so `/session-review` and ad-hoc
use can slice without bespoke `jq` — no assumptions about which streams
exist, since sibling issues (#1166 `workflow-states.jsonl`, #1168
`iteration-journal.jsonl`) land in parallel and may or may not be present in
any given worktree/checkout.

Field-name heterogeneity (documented, not papered over)
--------------------------------------------------------
`telemetry-schema.md` shows every stream uses slightly different field
names for the same *concept*. This module does not assume one canonical
schema; each facet tries a short, documented list of candidate field names
in priority order and uses the first one present on a given entry:

  * `--type` (event/category facet) tries, in order: `event` (e.g.
    `telemetry.jsonl`'s `command`/`skill`/`gate`), `type` (e.g.
    `config-changelog.jsonl`'s `amend`/`approval`/...), `hook` (e.g.
    `boundary-events.jsonl`, `gate-bypass.jsonl`, `refactor-freeze.jsonl`),
    `workflow` (e.g. `workflow-states.jsonl`'s `ship`/`autoship`/`build`).
    This order runs from the most stream-specific "this IS an event type"
    field name to the more generic ones, so a stream that happens to define
    both `event` and `hook` (none currently do) still resolves
    unambiguously.
  * `--gate-outcome` tries, in order: `decision` (e.g.
    `boundary-events.jsonl`'s `block`/`warn`/`bypass`/`intervention`/
    `revert`), then `outcome` (e.g. `telemetry.jsonl`'s `fired`/`bypassed`,
    `autoship-log.jsonl`'s `success`/`convergence_failure`). `decision`
    first because it is the more specific/deliberate name for a gate's
    verdict; `outcome` is the broader fallback used by streams with no
    dedicated `decision` field.
  * `--since` (inclusive lower bound) tries, in order: `ts`, then
    `timestamp`. Comparison is a plain lexical string compare, valid only
    because every emitter in this repo stamps `%Y-%m-%dT%H:%M:%SZ` UTC
    (confirmed against `boundary_events.py` and `workflow_state.py`), which
    sorts identically lexically and chronologically.
  * `--session` matches the `session_id` field only — every stream that
    carries a session join key names it identically.

All provided filters compose with AND. Malformed JSON lines are skipped,
not fatal — these streams are hand-authored-adjacent, append-only logs and
a single corrupt line must never break a query over the rest of the file.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

_TYPE_FIELDS = ("event", "type", "hook", "workflow")
_GATE_OUTCOME_FIELDS = ("decision", "outcome")
_TS_FIELDS = ("ts", "timestamp")


def _first_present(entry: dict, candidates) -> str | None:
    for field in candidates:
        if field in entry and entry[field] is not None:
            return entry[field]
    return None


def load_stream(path) -> Iterator[dict]:
    """Yield parsed JSON objects from a JSONL file, skipping malformed lines.

    Non-dict JSON values (e.g. a bare string or number on a line) are also
    skipped, since every stream is a sequence of JSON objects.
    """
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def filter_entries(
    entries: Iterable[dict],
    event_type: str | None = None,
    session_id: str | None = None,
    since: str | None = None,
    gate_outcome: str | None = None,
) -> Iterator[dict]:
    """Apply every provided filter (AND-composed) to `entries`, a pure filter.

    Each filter is skipped entirely when its argument is `None`, so calling
    with no filters is an identity pass-through.
    """
    for entry in entries:
        if event_type is not None:
            if _first_present(entry, _TYPE_FIELDS) != event_type:
                continue
        if session_id is not None:
            if entry.get("session_id") != session_id:
                continue
        if since is not None:
            ts = _first_present(entry, _TS_FIELDS)
            if not isinstance(ts, str) or ts < since:
                continue
        if gate_outcome is not None:
            if _first_present(entry, _GATE_OUTCOME_FIELDS) != gate_outcome:
                continue
        yield entry


def facet_count(entries: Iterable[dict], field: str) -> dict:
    """Value -> count breakdown of `field` across `entries`.

    Entries missing `field` are omitted from the result entirely (not
    counted under e.g. a `None` bucket) since an absent field is a schema
    mismatch, not a meaningful facet value.
    """
    counts: dict = {}
    for entry in entries:
        if field not in entry or entry[field] is None:
            continue
        value = entry[field]
        key = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _stream_path(cwd, stream: str) -> Path:
    base = Path(cwd) if cwd else Path.cwd()
    return base / "metrics" / f"{stream}.jsonl"


def cmd_query(args) -> int:
    path = _stream_path(args.cwd, args.stream)
    entries = list(
        filter_entries(
            load_stream(path),
            event_type=args.type,
            session_id=args.session,
            since=args.since,
            gate_outcome=args.gate_outcome,
        )
    )

    if args.facet:
        counts = facet_count(entries, args.facet)
        for value, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{value}\t{count}")
        return 0

    if args.format == "json-array":
        print(json.dumps(entries, indent=2))
    else:
        for entry in entries:
            print(json.dumps(entry, separators=(",", ":")))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cwd", default=None, help="Directory containing metrics/ (default: cwd)")
    ap.add_argument("--stream", required=True, help="Stream name, resolves to metrics/<name>.jsonl")
    ap.add_argument("--type", default=None, help="Event-type facet; see module docstring for field fallback order")
    ap.add_argument("--session", default=None, help="Filter on the session_id field")
    ap.add_argument("--since", default=None, help="ISO-8601 lower bound on the ts/timestamp field")
    ap.add_argument("--gate-outcome", dest="gate_outcome", default=None, help="Gate decision/outcome facet")
    ap.add_argument("--facet", default=None, help="Print value->count breakdown for this field instead of matches")
    ap.add_argument("--format", choices=["jsonl", "json-array"], default="jsonl")
    ap.set_defaults(func=cmd_query)

    parsed = ap.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
