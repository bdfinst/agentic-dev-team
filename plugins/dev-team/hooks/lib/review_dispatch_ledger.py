"""hooks/lib/review_dispatch_ledger.py — shared review-dispatch-ledger reading (#1998).

`review_value_coverage.py` and `contract_failure_report.py` both need the
same denominator: how many times each review agent was actually dispatched.
Both hand-rolled an identical `read_jsonl()` + `dispatch_counts()` pair over
`boundary-events.jsonl`'s `hook == "agent_dispatch_ledger"` / `decision ==
"record"` rows (see `agent_dispatch_ledger.py`) — the predicate "this row IS
a review dispatch" had three homes (the emitter plus two independent
readers) before this module. Per this repo's CLAUDE.md ratchet rule ("a
mechanical finding reported twice becomes a check"), two independent review
agents (arch-review, structure-review; #1998 wave 1) plus a third
(domain-review; #1998 wave 2) flagged the same duplication — this module is
the single extraction point, so a hook never reaches into `scripts/` (the
correct dependency direction is `scripts/` -> `hooks/lib/`, never the
reverse, per `review_agent_registry.py`'s own docstring) and neither reader
re-derives the ledger's wire shape by hand again.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths

#: The stream every review dispatch is deterministically recorded to.
LEDGER_STREAM = "boundary-events.jsonl"

#: The ledger rows that denote a review dispatch.
_LEDGER_HOOK = "agent_dispatch_ledger"
_LEDGER_DECISION = "record"


def resolve_stream(category: str, stream: str, cwd: Path, *, migrate: bool = False) -> Path:
    """Resolve a `.claude/<category>/<stream>` metrics path.

    `migrate=False` by default: every current caller of this helper is a
    read-only report/query, so a mere read must never migrate a legacy file
    or create `.claude/<category>/` as a side effect (mirrors
    `hooks/lib/metrics_query.py::_stream_path`'s same reasoning). Pass
    `migrate=True` explicitly for a writer.
    """
    return artifact_paths.resolve_file(category, stream, cwd, migrate=migrate)


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return (rows, malformed_count). Malformed lines are skipped but
    counted — silently dropping unreadable telemetry is the same class of
    defect #1998 exists to surface, so the count is reported, not swallowed.
    """
    rows: list[dict] = []
    malformed = 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return rows, malformed
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            malformed += 1
    return rows, malformed


def dispatch_counts(ledger_rows) -> Counter:
    """Per-agent dispatch counts from the deterministic ledger."""
    counts: Counter = Counter()
    for row in ledger_rows:
        if row.get("hook") != _LEDGER_HOOK:
            continue
        if row.get("decision") != _LEDGER_DECISION:
            continue
        agent = row.get("matched_rule")
        if isinstance(agent, str) and agent.strip():
            counts[agent.strip()] += 1
    return counts


__all__ = ("LEDGER_STREAM", "dispatch_counts", "read_jsonl", "resolve_stream")
